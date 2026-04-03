"""
Agent 3: LLM-as-Judge
Model: Qwen3.5-122B-A10B via Qubrid
Scores each output pair against expected behaviour
"""

import json
import re
import asyncio
from typing import List, Dict, Any
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from config.settings import JUDGE_MODEL, JUDGE_PROMPT, PASS_THRESHOLD

async def judge_test_case(test_case: Dict[str, Any], output_v1: str, output_v2: str) -> Dict[str, Any]:
    """Evaluates two outputs against expected behavior using an LLM Judge."""
    try:
        model = LiteLlm(model=JUDGE_MODEL)
        
        prompt = JUDGE_PROMPT.format(
            input=test_case.get("input", ""),
            expected_behaviour=test_case.get("expected_behaviour", ""),
            output_v1=output_v1,
            output_v2=output_v2
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
            
        print(f"DEBUG: Judge Raw Text: {response_text}")
        
        # Robust JSON extraction — handles multiple thinking-block formats and markdown fences
        try:
            # 1. Strip XML-style thinking blocks: <think>...</think>
            clean_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
            # 2. Strip plain-text thinking preambles (Qwen3.5 outputs "Thinking Process:\n...")
            #    Everything before the first standalone '{' on its own line is preamble.
            #    Strategy: find the LAST complete {...} blob — it's always the answer JSON.
            clean_text = re.sub(r'```(?:json)?', '', clean_text).replace('```', '').strip()

            # 3. Extract the LAST valid JSON object — model may emit prose after thinking
            #    Walk backwards from the final '}' to find its matching '{'
            end = clean_text.rfind('}')
            depth = 0
            start = -1
            for i in range(end, -1, -1):
                if clean_text[i] == '}':
                    depth += 1
                elif clean_text[i] == '{':
                    depth -= 1
                    if depth == 0:
                        start = i
                        break

            if start != -1 and end != -1:
                data = json.loads(clean_text[start:end + 1])
            else:
                data = json.loads(clean_text)
        except Exception:
            raise ValueError(f"Failed to parse JSON from: {response_text[:200]}...")
            
        return data
            
    except Exception as e:
        print(f"ERROR: Judge Exception: {type(e).__name__}: {str(e)}")
        return {
            "v1_scores": {"semantic_correctness": 0, "tone_appropriateness": 0, 
                          "completeness": 0, "safety": 0, "behaviour_match": 0},
            "v2_scores": {"semantic_correctness": 0, "tone_appropriateness": 0,
                          "completeness": 0, "safety": 0, "behaviour_match": 0},
            "v1_average": 0.0,
            "v2_average": 0.0,
            "verdict": "REGRESSION",
            "regression_reason": f"Judge error: {str(e)}",
            "recommendation": ""
        }

async def judge_all_results(
    test_cases: List[Dict[str, Any]],
    raw_outputs: List[Dict[str, Any]],
    pass_threshold: float = PASS_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Runs judgment in parallel for all test cases."""
    tasks = []
    
    for tc in test_cases:
        tc_id = tc.get("id")
        outputs = next((o for o in raw_outputs if o.get("test_case_id") == tc_id), None)
        
        if not outputs:
            continue
            
        tasks.append(judge_and_format(tc, outputs, pass_threshold))
        
    return await asyncio.gather(*tasks)

async def judge_and_format(
    tc: Dict[str, Any],
    output_pair: Dict[str, Any],
    pass_threshold: float,
) -> Dict[str, Any]:
    """Helper to judge a single test case and ensure it has necessary metadata."""
    v1_result = output_pair.get("v1_result", {})
    v2_result = output_pair.get("v2_result", {})
    v1_out = v1_result.get("output", "")
    v2_out = v2_result.get("output", "")
    v1_error = v1_result.get("error", "")
    v2_error = v2_result.get("error", "")

    if v1_error or v2_error:
        runner_error_message = " | ".join(
            part for part in [
                f"v1 runner error: {v1_error}" if v1_error else "",
                f"v2 runner error: {v2_error}" if v2_error else "",
            ] if part
        )
        result = {
            "v1_scores": {"semantic_correctness": 0, "tone_appropriateness": 0,
                          "completeness": 0, "safety": 0, "behaviour_match": 0},
            "v2_scores": {"semantic_correctness": 0, "tone_appropriateness": 0,
                          "completeness": 0, "safety": 0, "behaviour_match": 0},
            "v1_average": 0.0,
            "v2_average": 0.0,
            "verdict": "ERROR",
            "regression_reason": runner_error_message,
            "recommendation": "Check the runner model, API credentials, and network connectivity before trusting this result.",
        }
    else:
        result = await judge_test_case(tc, v1_out, v2_out)
    
    if result.get("verdict") != "ERROR":
        # Override verdict based on the configured threshold for this suite
        if result.get("v2_average", 0) < pass_threshold and result.get("v1_average", 0) >= pass_threshold:
            result["verdict"] = "REGRESSION"
        elif result.get("v2_average", 0) >= pass_threshold and result.get("v1_average", 0) < pass_threshold:
            result["verdict"] = "IMPROVEMENT"
        elif result.get("v2_average", 0) >= pass_threshold:
            result["verdict"] = "PASS"
        else:
            result["verdict"] = "FAIL"
        
    result["test_case_id"] = tc.get("id")
    result["category"] = tc.get("category", "")
    result["input"] = tc.get("input", "")
    result["expected_behaviour"] = tc.get("expected_behaviour", "")
    result["output_v1"] = v1_out
    result["output_v2"] = v2_out
    result["output_v1_error"] = v1_error
    result["output_v2_error"] = v2_error
    return result

def calculate_summary(judgments: list[dict]) -> dict:
    """
    Summarize the judgments list.
    """
    total = len(judgments)
    passed = sum(1 for j in judgments if j.get("verdict") == "PASS")
    regressions = sum(1 for j in judgments if j.get("verdict") == "REGRESSION")
    improvements = sum(1 for j in judgments if j.get("verdict") == "IMPROVEMENT")
    failures = sum(1 for j in judgments if j.get("verdict") == "FAIL")
    errors = sum(1 for j in judgments if j.get("verdict") == "ERROR")
    
    if total > 0:
        pass_rate = ((passed + improvements) / total) * 100
        avg_v1_score = sum(j.get("v1_average", 0) for j in judgments) / total
        avg_v2_score = sum(j.get("v2_average", 0) for j in judgments) / total
    else:
        pass_rate = 0.0
        avg_v1_score = 0.0
        avg_v2_score = 0.0
        
    return {
        "total": total,
        "passed": passed,
        "regressions": regressions,
        "improvements": improvements,
        "failures": failures,
        "errors": errors,
        "pass_rate": pass_rate,
        "avg_v1_score": avg_v1_score,
        "avg_v2_score": avg_v2_score,
        "has_regressions": regressions > 0,
        "is_clean_run": regressions == 0 and failures == 0 and errors == 0,
    }
