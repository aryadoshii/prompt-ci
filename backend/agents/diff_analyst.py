"""
Agent 1: Semantic Diff Analyst
Model: Qwen3-Coder-480B via Qubrid LiteLLM
Input: prompt_v1 (str), prompt_v2 (str)
Output: structured diff JSON
"""

import json
import re
from typing import Dict, Any
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from config.settings import DIFF_MODEL, DIFF_PROMPT

async def analyze_diff(prompt_v1: str, prompt_v2: str) -> Dict[str, Any]:
    """Analyzes semantic changes between two prompt versions."""
    try:
        model = LiteLlm(model=DIFF_MODEL)
        
        prompt = DIFF_PROMPT.format(
            prompt_v1=prompt_v1,
            prompt_v2=prompt_v2
        )
        
        # Prepare request with system instruction
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
            
        print(f"DEBUG: Diff Analyst Raw Text: {response_text}")
        # Strip <think> tags and plain-text thinking preambles, then markdown fences
        clean_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
        clean_text = re.sub(r'```(?:json)?', '', clean_text).replace('```', '').strip()

        # Walk backwards from the last '}' to find its matching '{' — handles nested objects
        end = clean_text.rfind('}')
        depth, start = 0, -1
        for i in range(end, -1, -1):
            if clean_text[i] == '}':
                depth += 1
            elif clean_text[i] == '{':
                depth -= 1
                if depth == 0:
                    start = i
                    break

        if start != -1 and end != -1:
            try:
                return json.loads(clean_text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return json.loads(clean_text)
        
    except Exception as e:
        print(f"ERROR: Diff Analyst Exception: {type(e).__name__}: {str(e)}")
        return {
            "changes": [
                {
                    "type": "parse_error",
                    "description": f"Failed to parse diff: {str(e)}",
                    "risk": "HIGH"
                }
            ],
            "high_risk_areas": ["all"],
            "overall_risk": "HIGH",
            "summary": "Diff analysis failed to execute or parse properly."
        }
