from .models import PipelineResult, TraceEvent, now_iso
from .prompts import PromptTemplates
from .answer_utils import extract_final_answer


ARCHITECTURE_VERSION = "single_v2_1_olympiad_direct"


def solve(problem: str, llm_client) -> PipelineResult:
    package = PromptTemplates.single_agent(problem)
    response = llm_client.generate(role="single", prompt=f"{package.system_prompt}\n\n{package.user_prompt}")
    answer = extract_final_answer(response)

    trace = [
        TraceEvent(now_iso(), "single_system_prompt", {"text": package.system_prompt}),
        TraceEvent(now_iso(), "single_user_prompt", {"text": package.user_prompt}),
        TraceEvent(now_iso(), "single_response", {"text": response}),
    ]

    return PipelineResult(
        mode="single",
        problem=problem,
        final_answer=answer,
        trace=trace,
        verdict="N/A",
    )
