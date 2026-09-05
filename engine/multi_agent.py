import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from .models import PipelineResult, TraceEvent, now_iso
from .prompts import PromptTemplates
from .answer_utils import extract_final_answer


ARCHITECTURE_VERSION = "multi_v5_0_dual_solver_symmetric_arbiter"

_NUMBER_PATTERN = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s*/\s*[-+]?\d+(?:\.\d+)?)?"
)


def _extract_verdict(text: str) -> str:
    marker = "VERDICT:"
    if marker in text:
        return text.split(marker, 1)[1].splitlines()[0].strip()
    return "UNKNOWN"


def _selected_option(verdict: str) -> str | None:
    normalized = re.sub(r"[^A-Z ]", "", str(verdict).upper()).strip()
    if "SELECT A" in normalized:
        return "A"
    if "SELECT B" in normalized:
        return "B"
    return None


def _numeric_value(value: str) -> Fraction | None:
    text = str(value).replace("−", "-").strip().strip("$*_")
    text = re.sub(r"(?:°|\\circ)\s*$", "", text).strip()
    scientific = re.fullmatch(
        r"([-+]?\d+(?:\.\d+)?)\s*(?:×|\\times|\*)\s*10\s*\^?\s*\{?\s*([-+]?\d+)\s*\}?",
        text,
    )
    if scientific:
        try:
            return Fraction(Decimal(scientific.group(1))) * (Fraction(10) ** int(scientific.group(2)))
        except (InvalidOperation, ValueError, ZeroDivisionError):
            return None
    latex_fraction = re.fullmatch(
        r"\\(?:d?frac)\{\s*([-+]?\d+(?:\.\d+)?)\s*\}\{\s*([-+]?\d+(?:\.\d+)?)\s*\}",
        text,
    )
    if latex_fraction:
        try:
            return Fraction(Decimal(latex_fraction.group(1))) / Fraction(
                Decimal(latex_fraction.group(2))
            )
        except (InvalidOperation, ValueError, ZeroDivisionError):
            return None
    if re.fullmatch(_NUMBER_PATTERN, text) is None:
        return None
    token = text.replace(",", "").replace(" ", "")
    try:
        if "/" in token:
            numerator, denominator = token.split("/", 1)
            return Fraction(Decimal(numerator)) / Fraction(Decimal(denominator))
        return Fraction(Decimal(token))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def _answers_equivalent(left: str, right: str) -> bool:
    left_number = _numeric_value(left)
    right_number = _numeric_value(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    def normalize(value: str) -> str:
        text = str(value).strip().casefold()
        text = text.replace("−", "-").replace("×", r"\times")
        text = text.replace(r"\left", "").replace(r"\right", "")
        text = re.sub(r"\\(?:,|!|;|quad|qquad)", "", text)
        text = re.sub(r"\s+", "", text)
        return text.strip("[]().$*_")

    return bool(normalize(left)) and normalize(left) == normalize(right)


def solve(problem: str, llm_client) -> PipelineResult:
    primary_pkg = PromptTemplates.planner_executor(problem)
    verifier_pkg = PromptTemplates.verifier(problem)

    # Both solvers are blind to one another and run concurrently. The primary
    # response still exposes its plan, but avoids a separate network round trip.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="math-agent") as pool:
        primary_future = pool.submit(
            llm_client.generate,
            role="executor",
            prompt=f"{primary_pkg.system_prompt}\n\n{primary_pkg.user_prompt}",
        )
        verifier_future = pool.submit(
            llm_client.generate,
            role="verifier",
            prompt=f"{verifier_pkg.system_prompt}\n\n{verifier_pkg.user_prompt}",
        )
        execution = primary_future.result()
        verification = verifier_future.result()

    candidate_answer = extract_final_answer(execution)
    verifier_answer = extract_final_answer(verification)

    trace = [
        TraceEvent(now_iso(), "planner_executor_system_prompt", {"text": primary_pkg.system_prompt}),
        TraceEvent(now_iso(), "planner_executor_user_prompt", {"text": primary_pkg.user_prompt}),
        TraceEvent(now_iso(), "planner_executor_output", {"text": execution}),
        TraceEvent(now_iso(), "verifier_system_prompt", {"text": verifier_pkg.system_prompt}),
        TraceEvent(now_iso(), "verifier_user_prompt", {"text": verifier_pkg.user_prompt}),
        TraceEvent(now_iso(), "verifier_output", {"text": verification}),
    ]

    if _answers_equivalent(candidate_answer, verifier_answer):
        final_answer = candidate_answer
        verdict = "CONSENSUS"
        critique = (
            "VERDICT: CONSENSUS\n"
            "The Executor and blind Verifier independently reached equivalent answers.\n"
            f"FINAL ANSWER: {final_answer}"
        )
        trace.append(TraceEvent(now_iso(), "critic_output", {"text": critique}))
    else:
        # A stable half-swap removes the systematic "Executor is Option A"
        # position cue while keeping runs exactly reproducible.
        verifier_first = int(hashlib.sha256(problem.encode("utf-8")).hexdigest(), 16) % 2 == 0
        if verifier_first:
            option_a_solution, option_a_answer = verification, verifier_answer
            option_b_solution, option_b_answer = execution, candidate_answer
            option_a_source, option_b_source = "verifier", "executor"
        else:
            option_a_solution, option_a_answer = execution, candidate_answer
            option_b_solution, option_b_answer = verification, verifier_answer
            option_a_source, option_b_source = "executor", "verifier"
        critic_pkg = PromptTemplates.critic(
            problem,
            option_a_solution,
            option_a_answer,
            option_b_solution,
            option_b_answer,
        )
        critique = llm_client.generate(
            role="critic",
            prompt=f"{critic_pkg.system_prompt}\n\n{critic_pkg.user_prompt}",
            context={"option_a": option_a_answer, "option_b": option_b_answer},
        )
        final_answer = extract_final_answer(critique)
        verdict = _extract_verdict(critique)
        selected = _selected_option(verdict)
        if selected == "A":
            final_answer = option_a_answer
        elif selected == "B":
            final_answer = option_b_answer
        trace.extend(
            [
                TraceEvent(now_iso(), "critic_system_prompt", {"text": critic_pkg.system_prompt}),
                TraceEvent(now_iso(), "critic_user_prompt", {"text": critic_pkg.user_prompt}),
                TraceEvent(
                    now_iso(),
                    "critic_option_mapping",
                    {"text": f"Option A source: {option_a_source}; Option B source: {option_b_source}"},
                ),
                TraceEvent(now_iso(), "critic_output", {"text": critique}),
            ]
        )

        matches_executor = _answers_equivalent(final_answer, candidate_answer)
        matches_verifier = _answers_equivalent(final_answer, verifier_answer)
        if not matches_executor and not matches_verifier:
            well_formed_correction = (
                "CORRECTED" in verdict.upper()
                and 0 < len(final_answer) <= 240
                and "VERDICT:" not in final_answer.upper()
            )
            if not well_formed_correction:
                final_answer = candidate_answer
                verdict = "MALFORMED ARBITER — EXECUTOR PRESERVED"
                trace.append(
                    TraceEvent(
                        now_iso(),
                        "deterministic_guardrail",
                        {
                            "text": "The Critic did not emit a usable A/B decision or compact corrected "
                            "answer. The Executor candidate was preserved to prevent an unsupported regression."
                        },
                    )
                )

    return PipelineResult(
        mode="multi",
        problem=problem,
        final_answer=final_answer,
        trace=trace,
        verdict=verdict,
    )
