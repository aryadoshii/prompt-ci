"""
Agent 2: Parallel Test Runner
Pattern: ParallelAgent — all test cases run simultaneously
Each sub-agent runs ONE test case against BOTH prompt versions
"""

import asyncio
from google.adk.agents import Agent, ParallelAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
from tools.llm_runner import run_prompt_pair

def create_test_runner_agent(test_cases: list[dict],
                              prompt_v1: str,
                              prompt_v2: str,
                              model_id: str) -> ParallelAgent:
    """
    Dynamically creates a ParallelAgent with one sub-agent per test case.
    Each sub-agent calls run_prompt_pair() for its assigned test case.
    """
    # Create the model using the model identifier.
    model = LiteLlm(model=model_id)

    agents = []
    
    # We dynamically create an agent for each test case
    for idx, tc in enumerate(test_cases):
        def _run_pair_tool(tc_dict=tc, v1=prompt_v1, v2=prompt_v2, runner_model=model_id) -> dict:
            return run_prompt_pair(test_case=tc_dict, prompt_v1=v1, prompt_v2=v2, model=runner_model)
        
        tool = FunctionTool(_run_pair_tool, name=f"run_test_case_tool_{idx}", description="Runs a single test case for PromptCI.")
        agent = Agent(name=f"TestCaseAgent_{tc.get('id', idx)}", model=model, tools=[tool])
        agents.append(agent)

    parallel_agent = ParallelAgent(name="Regression Test Runner", agents=agents)
    return parallel_agent

async def run_all_tests_parallel(
    test_cases: list[dict],
    prompt_v1: str,
    prompt_v2: str,
    model: str,
) -> list[dict]:
    """
    Uses asyncio.gather to run all test cases concurrently for non-blocking FastAPI execution.
    Returns list of raw output pairs per test case.
    """
    loop = asyncio.get_running_loop()
    
    tasks = []
    for tc in test_cases:
        # Wrap sync blocking code to be async-compatible
        tasks.append(
            loop.run_in_executor(
                None, 
                run_prompt_pair,
                tc,
                prompt_v1,
                prompt_v2,
                model
            )
        )
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results, replacing exceptions with valid dictionaries if needed
    final_results = []
    for res in results:
        if isinstance(res, Exception):
            final_results.append({
                "test_case_id": "Error",
                "v1_result": {"output": "", "error": str(res)},
                "v2_result": {"output": "", "error": str(res)}
            })
        else:
            final_results.append(res)
            
    return final_results
