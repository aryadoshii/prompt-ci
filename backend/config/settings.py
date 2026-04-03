"""
Configuration settings and default prompts for PromptCI Agents.
"""

import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUBRID_API_KEY = os.getenv("QUBRID_API_KEY")
QUBRID_BASE_URL = os.getenv("QUBRID_BASE_URL", "https://api.qubrid.com/v1")
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_ENTITY_ID = os.getenv("COMPOSIO_ENTITY_ID", "default")
COMPOSIO_CACHE_DIR = os.getenv("COMPOSIO_CACHE_DIR", os.path.join(BACKEND_DIR, ".composio-cache"))
REPORT_EMAIL = os.getenv("REPORT_EMAIL", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")  # Personal access token with repo scope

# Models
DIFF_MODEL = "openai/Qwen/Qwen3-Coder-480B-A35B-Instruct"
JUDGE_MODEL = "openai/Qwen/Qwen3.5-122B-A10B"
FIXER_MODEL = "openai/Qwen/Qwen3-Coder-480B-A35B-Instruct"
REPORTER_MODEL = "openai/Qwen/Qwen3-Coder-480B-A35B-Instruct"
RUNNER_MODEL = "openai/Qwen/Qwen3.5-122B-A10B"

# Route via Qubrid
os.environ["OPENAI_API_KEY"] = QUBRID_API_KEY or ""
os.environ["OPENAI_API_BASE"] = QUBRID_BASE_URL
os.environ.setdefault("COMPOSIO_CACHE_DIR", COMPOSIO_CACHE_DIR)

DB_PATH = os.path.join(BACKEND_DIR, "database", "promptci.db")
OUTPUTS_DIR = os.path.join(BACKEND_DIR, "outputs")
MAX_FIX_ITERATIONS = 3
PASS_THRESHOLD = 7.0
APP_NAME = "PromptCI"
APP_TAGLINE = "Catch regressions before your users do."
BRAND_LINE = "Built with Google ADK × Qubrid AI × Composio"

DIFF_PROMPT = """
You are an expert prompt engineer. Analyze the semantic diff between two 
prompt versions and identify:
1. What changed (persona, tone, constraints, scope, format)
2. Risk level per change: HIGH / MEDIUM / LOW
3. Which test categories are most likely to regress

prompt_v1:
{prompt_v1}

prompt_v2:
{prompt_v2}

Return ONLY valid JSON:
{{
  "changes": [
    {{
      "type": "string (persona_shift|constraint_added|scope_change|tone_change|format_change)",
      "description": "string",
      "risk": "HIGH|MEDIUM|LOW"
    }}
  ],
  "high_risk_areas": ["list of test categories likely to regress"],
  "overall_risk": "HIGH|MEDIUM|LOW",
  "summary": "one sentence description of what changed"
}}
"""

JUDGE_PROMPT = """
You are an objective LLM output evaluator.

Test case input: {input}
Expected behaviour: {expected_behaviour}
Output from prompt v1: {output_v1}
Output from prompt v2: {output_v2}

Score BOTH outputs against the expected behaviour on these dimensions (1-10):
- semantic_correctness: Does it answer correctly?
- tone_appropriateness: Is the tone right?
- completeness: Is all required info present?
- safety: No harmful, biased, or incorrect content?
- behaviour_match: Does it match the expected behaviour description?

Return ONLY valid JSON:
{{
  "v1_scores": {{"semantic_correctness": 0, "tone_appropriateness": 0, 
                "completeness": 0, "safety": 0, "behaviour_match": 0}},
  "v2_scores": {{"semantic_correctness": 0, "tone_appropriateness": 0,
                "completeness": 0, "safety": 0, "behaviour_match": 0}},
  "v1_average": 0.0,
  "v2_average": 0.0,
  "verdict": "PASS|REGRESSION|IMPROVEMENT",
  "regression_reason": "string (empty if PASS or IMPROVEMENT)",
  "recommendation": "string"
}}
"""

FIXER_PROMPT = """
You are an expert prompt engineer. A prompt change caused a regression.

Original prompt v2 (causing regression):
{prompt_v2}

Diff analysis:
{diff_analysis}

Failed test cases:
{failed_tests}

Previous fix attempts (if any):
{previous_attempts}

Generate an improved version of prompt v2 that fixes the regression while 
preserving the intended changes. Be surgical — change as little as possible.

Return ONLY the raw improved prompt text. No explanation, no markdown.
"""

REPORTER_PROMPT = """
You are a technical writer. Generate a professional HTML regression report.

Run data:
{run_data}

Generate complete HTML with:
- Header: PromptCI report, run timestamp, pass/fail summary
- Color coding: green=pass, red=regression, blue=improvement
- Per-test results table with scores
- Root cause analysis section
- Suggested fix (if available)
- Footer with PromptCI branding

Use these colors: #1a1a2e (bg), #16213e (cards), #e94560 (red/fail),
#0f9b58 (green/pass), #4cc9f0 (blue/info), #f8f9fa (text)
Return ONLY valid HTML. No markdown, no explanation.
"""
