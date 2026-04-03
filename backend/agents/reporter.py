"""
Agent 5: HTML Report Generator
Model: gpt-oss-120b via Qubrid
Generates the complete HTML regression report
"""

import os
import json
from google.adk.models.lite_llm import LiteLlm
from config.settings import REPORTER_MODEL, REPORTER_PROMPT, OUTPUTS_DIR
from google.adk.models.llm_request import LlmRequest
from google.genai import types

async def generate_html_report(
    run_id: str,
    prompt_file: str,
    prompt_v1: str,
    prompt_v2: str,
    diff_analysis: dict,
    judgments: list[dict],
    summary: dict,
    fix_result: dict,
    timestamp: str,
) -> str:
    """Calls Qubrid with REPORTER_PROMPT + all run data."""
    try:
        model = LiteLlm(model=REPORTER_MODEL)
        
        run_data = {
            "run_id": run_id,
            "timestamp": timestamp,
            "prompt_file": prompt_file,
            "prompt_v1": prompt_v1,
            "prompt_v2": prompt_v2,
            "summary": summary,
            "diff_analysis": diff_analysis,
            "fix_result": fix_result,
            "judgments": judgments,
        }
        
        prompt = REPORTER_PROMPT.format(run_data=json.dumps(run_data))
        request = LlmRequest(
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
        )
        
        # Generator for result
        response_text = ""
        async for chunk in model.generate_content_async(request):
            if chunk.content and chunk.content.parts:
                for part in chunk.content.parts:
                    if part.text:
                        response_text += part.text
            
        print(f"DEBUG: Reporter Raw Text: {response_text}")
        html = response_text
        
        if "```html" in html:
            html = html.split("```html")[1].split("```")[0]
        elif "```" in html:
            html = html.split("```")[1].split("```")[0]
            
        return html.strip()
    except Exception as e:
        print(f"ERROR: Reporter Exception: {type(e).__name__}: {str(e)}")
        return fallback_template(summary, judgments)

def fallback_template(summary: dict, judgments: list[dict]) -> str:
    """Fallback if the model call fails — renders a minimal but complete report."""
    rows = ""
    for j in judgments:
        verdict = j.get("verdict", "")
        color_map = {
            "PASS": "#0f9b58",
            "REGRESSION": "#e94560",
            "IMPROVEMENT": "#4cc9f0",
            "FAIL": "#f59e0b",
            "ERROR": "#f97316",
        }
        color = color_map.get(verdict, "#4cc9f0")
        rows += (
            f"<tr><td>{j.get('test_case_id', '')}</td>"
            f"<td>{j.get('category', '')}</td>"
            f"<td style='color:{color}'>{verdict}</td>"
            f"<td>{j.get('v1_average', 0):.1f}</td>"
            f"<td>{j.get('v2_average', 0):.1f}</td>"
            f"<td>{j.get('regression_reason', '') or j.get('recommendation', '')}</td></tr>"
        )
    html = f"""<!DOCTYPE html>
<html>
<head><style>
body{{background:#1a1a2e;color:#f8f9fa;font-family:sans-serif;padding:20px;}}
.card{{background:#16213e;padding:15px;border-radius:8px;margin-bottom:20px;}}
table{{width:100%;border-collapse:collapse;}} th,td{{padding:8px;border:1px solid #333;text-align:left;}}
th{{background:#16213e;}}
</style></head>
<body>
<h1>PromptCI Regression Report</h1>
<div class="card">
  <h2>Summary</h2>
  <p>Pass Rate: {summary.get("pass_rate", 0):.1f}%</p>
  <p>Passed: {summary.get("passed", 0)} / {summary.get("total", 0)}</p>
  <p>Regressions: <span style="color:#e94560">{summary.get("regressions", 0)}</span></p>
  <p>Improvements: <span style="color:#4cc9f0">{summary.get("improvements", 0)}</span></p>
  <p>Failures: <span style="color:#f59e0b">{summary.get("failures", 0)}</span></p>
  <p>Errors: <span style="color:#f97316">{summary.get("errors", 0)}</span></p>
</div>
<div class="card">
  <h2>Test Results</h2>
  <table><tr><th>ID</th><th>Category</th><th>Verdict</th><th>V1 Score</th><th>V2 Score</th><th>Reason</th></tr>
  {rows}
  </table>
</div>
<footer style="color:#888;margin-top:20px">Built with Google ADK × Qubrid AI × Composio</footer>
</body></html>"""
    return html

def save_report(html: str, run_id: str) -> str:
    """
    Saves HTML to outputs/{run_id}.html
    Returns file path.
    """
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUTS_DIR, f"{run_id}.html")
    
    with open(filepath, 'w') as f:
        f.write(html)
        
    return filepath
