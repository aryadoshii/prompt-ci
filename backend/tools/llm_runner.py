"""
Executes a prompt + input against a specified model via Qubrid API.
Used by the ParallelAgent test runner.
"""

import os
from openai import OpenAI
import time

from config.settings import RUNNER_MODEL

# Ensure environment variables are loaded from the actual settings
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE"),
)

def run_prompt(
    system_prompt: str,
    user_input: str,
    model: str = RUNNER_MODEL,
    temperature: float = 0.0,
) -> dict:
    """
    Execute a prompt against Qubrid API.
    Returns {"output": str, "tokens": int, "latency_ms": float, "error": str}
    """
    start_time = time.time()
    try:
        # Strip LiteLLM-style "openai/" prefix — Qubrid expects "Qwen/ModelName" not "openai/Qwen/ModelName"
        model_id = model.removeprefix("openai/")
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=temperature,
            timeout=30.0,
        )
        latency = (time.time() - start_time) * 1000
        message = response.choices[0].message
        
        # Robustly capture content or reasoning_content (Qwen)
        output = getattr(message, 'content', "") or ""
        reasoning = getattr(message, 'reasoning_content', "") or ""
        
        # If content is empty but reasoning has text, use reasoning as primary output for test purposes
        if not output.strip() and reasoning.strip():
            output = reasoning
            
        tokens = response.usage.total_tokens if response.usage else 0
        
        return {
            "output": output.strip(),
            "tokens": tokens,
            "latency_ms": latency,
            "error": ""
        }
    except Exception as e:
        return {
            "output": "",
            "tokens": 0,
            "latency_ms": (time.time() - start_time) * 1000,
            "error": str(e)
        }

def run_prompt_pair(
    test_case: dict,
    prompt_v1: str,
    prompt_v2: str,
    model: str = RUNNER_MODEL,
) -> dict:
    """
    Run a single test case against both prompt versions sequentially or simultaneously.
    Returns outputs for both v1 and v2.
    """
    input_text = test_case.get("input", "")
    
    # Run v1
    v1_result = run_prompt(system_prompt=prompt_v1, user_input=input_text, model=model)
    
    # Run v2
    v2_result = run_prompt(system_prompt=prompt_v2, user_input=input_text, model=model)
    
    return {
        "test_case_id": test_case.get("id"),
        "v1_result": v1_result,
        "v2_result": v2_result
    }
