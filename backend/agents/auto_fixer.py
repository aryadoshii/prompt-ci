"""
Agent 4: LoopAgent Auto-Fixer
Model: Qwen3-Coder-480B via Qubrid
Iterates prompt fixes until regressions resolve or max iterations reached
"""

import json
from typing import List, Dict, Any
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from config.settings import FIXER_MODEL, FIXER_PROMPT, MAX_FIX_ITERATIONS, PASS_THRESHOLD, RUNNER_MODEL
from agents.test_runner import run_all_tests_parallel
from agents.judge import judge_all_results

async def fix_regression(
    prompt_v2: str,
    diff_analysis: Dict[str, Any],
    failed_tests: List[Dict[str, Any]],
    previous_attempts: List[str] = None
) -> str:
    """Uses LLM Fixer to generate a better version of prompt v2."""
    try:
        model = LiteLlm(model=FIXER_MODEL)
        
        prompt = FIXER_PROMPT.format(
            prompt_v2=prompt_v2,
            diff_analysis=json.dumps(diff_analysis),
            failed_tests=json.dumps(failed_tests),
            previous_attempts=json.dumps(previous_attempts or [])
        )
        
        request = LlmRequest(
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
        )
        
        response_text = ""
        async for chunk in model.generate_content_async(request):
            if chunk.content and chunk.content.parts:
                for part in chunk.content.parts:
                    if part.text:
                        response_text += part.text
            
        print(f"DEBUG: Fixer Raw Text: {response_text}")
        # Assuming the model follows instructions to return raw text
        return response_text.replace("```text", "").replace("```", "").strip()
        
    except Exception:
        return prompt_v2

async def run_fix_loop(
    prompt_v1: str,
    prompt_v2: str,
    diff_analysis: Dict[str, Any],
    test_cases: List[Dict[str, Any]],
    runner_model: str = RUNNER_MODEL,
    pass_threshold: float = PASS_THRESHOLD,
    max_iterations: int = MAX_FIX_ITERATIONS,
) -> Dict[str, Any]:
    """Iteratively attempts to fix regressions until PASS or MAX_FIX_ITERATIONS."""
    
    current_prompt = prompt_v2
    attempts = []
    judgments = []
    
    for i in range(max_iterations):
        # 1. Run tests with current prompt
        raw_outputs = await run_all_tests_parallel(
            test_cases=test_cases,
            prompt_v1=prompt_v1,
            prompt_v2=current_prompt,
            model=runner_model
        )
        
        # 2. Judge results
        judgments = await judge_all_results(test_cases, raw_outputs, pass_threshold=pass_threshold)
        
        blocking_failures = [
            j for j in judgments
            if j.get("verdict") in {"REGRESSION", "FAIL", "ERROR"}
        ]
        
        if not blocking_failures:
            return {
                "status": "resolved",
                "fixed_prompt": current_prompt,
                "iterations": i + 1,
                "final_judgments": judgments
            }
            
        # 3. Try to fix
        current_prompt = await fix_regression(current_prompt, diff_analysis, blocking_failures, attempts)
        attempts.append(current_prompt)
        
    return {
        "status": "unresolvable",
        "fixed_prompt": current_prompt,
        "iterations": max_iterations,
        "final_judgments": judgments
    }
