"""
FastAPI Routes for PromptCI.
"""

import uuid
import subprocess
import os
import hashlib
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from database.db import (
    create_run, update_run_status, complete_run, save_test_result,
    get_run, get_test_results, get_recent_runs, update_approval_status,
    get_stats
)
from agents.diff_analyst import analyze_diff
from agents.test_runner import run_all_tests_parallel
from agents.judge import judge_all_results, calculate_summary
from agents.auto_fixer import run_fix_loop
from agents.reporter import generate_html_report, save_report
from tools.email_tools import send_report_email, get_gmail_status
from config.settings import RUNNER_MODEL, GITHUB_TOKEN, MAX_FIX_ITERATIONS, PASS_THRESHOLD

router = APIRouter()

class RunPayload(BaseModel):
    prompt_v1: str
    prompt_v2: str
    prompt_file: str
    test_suite: Dict[str, Any]
    repo_path: str
    notify_email: Optional[str] = None

class ApprovePayload(BaseModel):
    action: str

async def run_pipeline_background(run_id: str, payload: RunPayload):
    """Background task to execute the 5-agent pipeline."""
    try:
        test_cases = payload.test_suite.get("test_cases", [])
        suite_settings = payload.test_suite.get("settings", {})
        runner_model = payload.test_suite.get("model") or RUNNER_MODEL
        pass_threshold = float(suite_settings.get("pass_threshold", PASS_THRESHOLD))
        max_fix_iterations = int(suite_settings.get("max_fix_iterations", MAX_FIX_ITERATIONS))
        
        # 1. Diff Analyst
        diff_analysis = await analyze_diff(payload.prompt_v1, payload.prompt_v2)
        
        # 2. Parallel Tests — use model from promptci.yaml if specified
        raw_outputs = await run_all_tests_parallel(
            test_cases=test_cases,
            prompt_v1=payload.prompt_v1,
            prompt_v2=payload.prompt_v2,
            model=runner_model
        )
        
        # 3. LLM Judge
        judgments = await judge_all_results(
            test_cases,
            raw_outputs,
            pass_threshold=pass_threshold,
        )
        
        failed_tests = [j for j in judgments if j.get("verdict") == "REGRESSION"]
        
        # 4. Auto-Fixer
        if failed_tests and payload.test_suite.get("settings", {}).get("auto_fix", True):
            fix_result = await run_fix_loop(
                prompt_v1=payload.prompt_v1,
                prompt_v2=payload.prompt_v2,
                diff_analysis=diff_analysis,
                test_cases=test_cases,
                runner_model=runner_model,
                pass_threshold=pass_threshold,
                max_iterations=max_fix_iterations,
            )
            # If fix succeeded, update judgments with the final test run from loop
            if fix_result["status"] == "resolved":
                judgments = fix_result["final_judgments"]
        else:
            fix_result = {
                "status": "no_fix_needed",
                "fixed_prompt": "",
                "iterations": 0,
                "final_judgments": judgments
            }
            
        summary = calculate_summary(judgments)
        
        # 5. Reporter
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html_report = await generate_html_report(
            run_id=run_id,
            prompt_file=payload.prompt_file,
            prompt_v1=payload.prompt_v1,
            prompt_v2=payload.prompt_v2,
            diff_analysis=diff_analysis,
            judgments=judgments,
            summary=summary,
            fix_result=fix_result,
            timestamp=timestamp
        )
        report_path = save_report(html_report, run_id)
        
        # DB Updates
        complete_run(run_id, summary, fix_result, report_path)
        for judgment in judgments:
            save_test_result(run_id, judgment.get("test_case_id"), judgment)
            
        # Email Delivery
        if payload.notify_email:
            subject = f"PromptCI Report — {summary.get('passed')}/{summary.get('total')} passed · {timestamp}"
            send_report_email(
                to=payload.notify_email,
                subject=subject,
                html_body=html_report,
                run_id=run_id
            )
            
    except Exception as e:
        update_run_status(run_id, "failed")
        print(f"Pipeline failed for {run_id}: {str(e)}")


@router.post("/run")
async def start_run(payload: RunPayload, background_tasks: BackgroundTasks):
    run_id = str(uuid.uuid4())
    v1_hash = hashlib.sha256(payload.prompt_v1.encode()).hexdigest()
    v2_hash = hashlib.sha256(payload.prompt_v2.encode()).hexdigest()
    
    create_run(run_id, payload.prompt_file, v1_hash, v2_hash, payload.repo_path)
    background_tasks.add_task(run_pipeline_background, run_id, payload)
    
    return {"run_id": run_id, "status": "running"}

@router.get("/run/{run_id}")
async def get_run_details(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    results = get_test_results(run_id)
    return {"run": run, "passed": run.get("passed"), "total": run.get("total_tests"), 
            "pass_rate": run.get("pass_rate"), "regressions": run.get("regressions"),
            "improvements": run.get("improvements"), "failures": run.get("failures"),
            "errors": run.get("errors"), "id": run.get("id"),
            "has_fix": run.get("has_fix") == 1, "fix_status": run.get("fix_status"),
            "fix_iterations": run.get("fix_iterations"), "status": run.get("status"),
            "test_results": results}

@router.get("/run/{run_id}/report")
async def get_run_report(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    path = run.get("report_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not generated yet or missing")
        
    with open(path, 'r') as f:
        html = f.read()
    
    return {"html": html}

@router.post("/run/{run_id}/approve")
async def approve_fix(run_id: str, payload: ApprovePayload):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    if payload.action == "dismiss":
        update_approval_status(run_id, "dismissed")
        return {"success": True}
        
    if payload.action == "approve":
        fixed_prompt = run.get("fixed_prompt")
        prompt_file = run.get("prompt_file")
        repo_path = run.get("repo_path") or os.path.dirname(prompt_file)

        if not fixed_prompt or run.get("has_fix") != 1:
            raise HTTPException(status_code=400, detail="No fix available to approve")

        try:
            # 1. Write the fix to the actual file on disk
            with open(prompt_file, "w") as f:
                f.write(fixed_prompt)

            branch_name = f"promptci/fix-{run_id[:8]}"
            commit_msg = (
                f"fix(prompt): PromptCI auto-fix — {run.get('regressions')} regressions resolved\n\n"
                f"Run ID: {run_id}\n"
                f"Auto-generated by PromptCI"
            )

            # 2. Get the authenticated remote URL (inject token so push works over HTTPS)
            remote_result = subprocess.run(
                ["git", "-C", repo_path, "remote", "get-url", "origin"],
                capture_output=True, timeout=10
            )
            remote_url = remote_result.stdout.decode().strip()

            # Inject GITHUB_TOKEN into the remote URL for authenticated push
            if GITHUB_TOKEN and remote_url.startswith("https://github.com/"):
                authed_url = remote_url.replace(
                    "https://github.com/",
                    f"https://x-access-token:{GITHUB_TOKEN}@github.com/"
                )
            else:
                authed_url = remote_url  # SSH remote — token not needed

            # 3. Git operations
            subprocess.run(["git", "-C", repo_path, "checkout", "-b", branch_name],
                           check=True, capture_output=True, timeout=30)
            subprocess.run(["git", "-C", repo_path, "add", prompt_file],
                           check=True, capture_output=True, timeout=30)
            subprocess.run(["git", "-C", repo_path, "commit", "-m", commit_msg],
                           check=True, capture_output=True, timeout=30)
            subprocess.run(["git", "-C", repo_path, "push", authed_url, branch_name],
                           check=True, capture_output=True, timeout=60)

            # 4. Create GitHub PR via API (if token is available)
            pr_url = ""
            if GITHUB_TOKEN and "github.com" in remote_url:
                import urllib.request, json as _json
                # Extract owner/repo from remote URL
                # Handles: https://github.com/owner/repo.git  or  git@github.com:owner/repo.git
                repo_slug = remote_url.rstrip("/").rstrip(".git")
                repo_slug = repo_slug.split("github.com/")[-1].split("github.com:")[-1]
                owner, repo_name = repo_slug.split("/")[:2]

                # Get the default branch to use as PR base
                default_branch_result = subprocess.run(
                    ["git", "-C", repo_path, "symbolic-ref", "refs/remotes/origin/HEAD"],
                    capture_output=True, timeout=10
                )
                default_branch = default_branch_result.stdout.decode().strip().split("/")[-1] or "main"

                pr_body = _json.dumps({
                    "title": f"PromptCI: Auto-fix {run.get('regressions')} regression(s) [{run_id[:8]}]",
                    "body": (
                        f"## PromptCI Auto-Fix\n\n"
                        f"**Run ID:** `{run_id}`\n"
                        f"**Regressions fixed:** {run.get('regressions')}\n"
                        f"**Fix iterations:** {run.get('fix_iterations')}\n\n"
                        f"This PR was automatically generated by PromptCI after detecting "
                        f"prompt regressions and successfully resolving them.\n\n"
                        f"---\n*Built with PromptCI — pytest for prompts*"
                    ),
                    "head": branch_name,
                    "base": default_branch,
                }).encode()

                req = urllib.request.Request(
                    f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
                    data=pr_body,
                    headers={
                        "Authorization": f"Bearer {GITHUB_TOKEN}",
                        "Accept": "application/vnd.github+json",
                        "Content-Type": "application/json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    pr_data = _json.loads(resp.read())
                    pr_url = pr_data.get("html_url", "")

            update_approval_status(run_id, "approved")
            return {"success": True, "branch": branch_name, "pr_url": pr_url, "error": ""}

        except subprocess.CalledProcessError as e:
            update_approval_status(run_id, "failed")
            return {"success": False, "branch": "", "pr_url": "", "error": e.stderr.decode()}
        except Exception as e:
            update_approval_status(run_id, "failed")
            return {"success": False, "branch": "", "pr_url": "", "error": str(e)}

@router.get("/health")
async def health_check():
    gmail_status = get_gmail_status()
    return {
        "status": "ok",
        "gmail_connected": gmail_status.get("connected"),
        "db": "ok"
    }

@router.get("/runs")
async def get_runs_list():
    return get_recent_runs()

@router.get("/stats")
async def get_system_stats():
    return get_stats()
