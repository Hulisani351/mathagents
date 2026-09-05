from dataclasses import dataclass


@dataclass(frozen=True)
class PromptPackage:
    system_prompt: str
    user_prompt: str


class PromptTemplates:
    @staticmethod
    def single_agent(problem: str) -> PromptPackage:
        return PromptPackage(
            system_prompt=(
                "You are an expert mathematical problem solver. Solve the supplied question carefully. "
                "For Olympiad problems, identify the relevant algebraic, geometric, number-theoretic, "
                "or combinatorial structure; preserve exact forms; check all constraints and edge cases; "
                "and give only the requested value or expression as the final answer."
            ),
            user_prompt=f"Problem:\n{problem}\n\nEnd with: FINAL ANSWER: [answer]",
        )

    @staticmethod
    def planner(problem: str) -> PromptPackage:
        return PromptPackage(
            system_prompt=(
                "You are the Planner. Translate the exact question into a mathematical model before "
                "planning calculations. Classify the mathematical domain, identify the requested quantity "
                "and every constraint, select the most relevant theorem or invariant, and plan an "
                "independent final check. Do not solve it yet."
            ),
            user_prompt=(
                f"Problem:\n{problem}\n\nReturn 3-7 numbered sub-goals. Include a final check for "
                "domain restrictions, boundary cases, exact-form simplification, and whether the result "
                "answers the requested quantity. Keep each sub-goal concise."
            ),
        )

    @staticmethod
    def planner_executor(problem: str) -> PromptPackage:
        return PromptPackage(
            system_prompt=(
                "You are the primary Planner-Solver. First build a short mathematical plan internally, "
                "then execute it accurately. Identify the requested quantity and all constraints, choose "
                "the governing theorem or invariant, preserve exact forms, and correct your plan if the "
                "calculation exposes a flaw. Your response must be independently checkable."
            ),
            user_prompt=(
                f"Problem:\n{problem}\n\nReturn two concise sections: PLAN with 2-5 numbered steps, "
                "then SOLUTION with the derivation. Check for extraneous roots, omitted solutions, signs, "
                "parity, divisibility, invalid geometric assumptions, double-counting, domain restrictions, "
                "and unnecessary decimal approximation whenever relevant. Finish with a substitution, "
                "boundary, invariant, or independent arithmetic check. End with the exact plain-text marker "
                "FINAL ANSWER: [answer]."
            ),
        )

    @staticmethod
    def executor(problem: str, plan: str) -> PromptPackage:
        return PromptPackage(
            system_prompt=(
                "You are the Executor. Solve the original problem using the plan, but correct the plan "
                "if necessary. Define variables, justify the governing theorem or construction, preserve "
                "exact symbolic forms, and perform a final substitution, boundary, or consistency check."
            ),
            user_prompt=(
                f"Problem:\n{problem}\n\nPlan:\n{plan}\n\n"
                "Before answering, check these common traps: extraneous roots; omitted solutions; sign, "
                "parity, divisibility, and modular errors; invalid geometric assumptions; double-counting; "
                "and decimal approximations where an exact form is required. Use a concise derivation. "
                "End with the exact plain-text marker FINAL ANSWER: [answer]."
            ),
        )

    @staticmethod
    def verifier(problem: str) -> PromptPackage:
        return PromptPackage(
            system_prompt=(
                "You are an expert mathematical problem solver acting as a blind Verifier. Independently "
                "solve the supplied question. You have not seen the Planner or Executor. Prefer a different "
                "method when possible, check constraints and exact form, and give only the requested value "
                "or expression as the final answer."
            ),
            user_prompt=(
                f"Problem:\n{problem}\n\nSolve from scratch, then verify by substitution, a small-case "
                "check, an invariant, or an independent calculation as appropriate. End with the exact "
                "plain-text marker FINAL ANSWER: [answer]."
            ),
        )

    @staticmethod
    def arbiter_guardrail(
        problem: str,
        candidate_answer: str,
        verifier_answer: str,
        arbitration: str,
    ) -> PromptPackage:
        return PromptPackage(
            system_prompt=(
                "You are a constrained arbitration guardrail. The previous Arbiter introduced a third "
                "answer unsupported by either independent solver. Select the better-supported original "
                "answer; do not invent another value."
            ),
            user_prompt=(
                f"Problem:\n{problem}\n\nOption A — Executor:\n{candidate_answer}\n\n"
                f"Option B — Blind Verifier:\n{verifier_answer}\n\nPrevious arbitration:\n{arbitration}\n\n"
                "Recheck the original wording and choose exactly Option A or Option B. Return "
                "VERDICT: CORRECT for Option A or VERDICT: CORRECTED for Option B, then end with the "
                "chosen value using FINAL ANSWER: [answer]."
            ),
        )

    @staticmethod
    def critic(
        problem: str,
        option_a_solution: str,
        option_a_answer: str,
        option_b_solution: str,
        option_b_answer: str,
    ) -> PromptPackage:
        return PromptPackage(
            system_prompt=(
                "You are the Critic and final Arbiter. Two anonymised solvers produced different answers. "
                "Their order is random and neither option is privileged. Do not reward length, confidence, "
                "or position. Independently recompute the smallest decisive calculation before selecting."
            ),
            user_prompt=(
                f"Problem:\n{problem}\n\nOption A solution:\n{option_a_solution}\n\n"
                f"Option A answer:\n{option_a_answer}\n\nOption B solution:\n{option_b_solution}\n\n"
                f"Option B answer:\n{option_b_answer}\n\n"
                "Adjudication checklist:\n"
                "1. State exactly what quantity the question asks for.\n"
                "2. Compute the shortest governing equation yourself, without copying either option.\n"
                "3. Check every domain restriction and any sign, parity, divisibility, geometric, or "
                "double-counting issue relevant to the problem.\n"
                "4. Substitute or recompute both proposed final values explicitly; show the arithmetic.\n"
                "5. Verify exact-form equivalence and reject extraneous or omitted solutions.\n"
                "Return VERDICT: SELECT A or VERDICT: SELECT B. If both are wrong, return "
                "VERDICT: CORRECTED only after deriving the correction independently. Use a concise "
                "adjudication and end with the exact marker FINAL ANSWER: [answer]."
            ),
        )
