"""Module 5's deterministic execution policy — every tunable constant and
non-LLM decision rule the interview graph depends on, in one reviewable
place. Nothing in this file calls Gemini; that's the point (module §12,
§13: "do NOT let an LLM freely decide the difficulty," "use explicit
transition rules... avoid letting an LLM return arbitrary graph
transitions").
"""

from app.models.enums import DifficultyLevel, DifficultySignal, RoundType

# --- Round length -----------------------------------------------------------
# Module 4's `template_rounds` schema (approved, not reopened here) has no
# "target question count" column — round length is therefore an execution
# -engine POLICY, not a plan attribute. One place to tune it.
DEFAULT_QUESTIONS_PER_ROUND: dict[RoundType, int] = {
    RoundType.INTRODUCTION: 1,
    RoundType.TECHNICAL: 3,
    RoundType.BEHAVIORAL: 2,
    RoundType.RESUME_DISCUSSION: 2,
    RoundType.SYSTEM_DESIGN: 2,
    RoundType.FINAL: 1,
    # RoundType.CODING is never reached — see CODING_ROUND_SKIP_REASON below.
}

# --- Follow-ups ---------------------------------------------------------
# Hard cap so a shallow-answer streak can never loop indefinitely
# (module §8: "limit follow-up loops... do not allow infinite questioning").
MAX_FOLLOW_UPS_PER_QUESTION = 2

# --- Adaptive difficulty -------------------------------------------------
# Deterministic policy over the two numeric signals Evaluation Agent
# already produces (technical_score, problem_solving_score) — never an
# LLM-proposed difficulty. The 40-80 dead zone is the anti-oscillation
# mechanism (module §12: "avoid oscillation"): a single so-so answer never
# flips the difficulty, only a clearly strong or clearly weak one does.
_DIFFICULTY_INCREASE_THRESHOLD = 80.0
_DIFFICULTY_DECREASE_THRESHOLD = 40.0

_DIFFICULTY_ORDER = [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD]


def compute_difficulty_signal(
    *, technical_score: float, problem_solving_score: float
) -> DifficultySignal:
    """Pure function — score in, signal out. No state, no side effects, no
    knowledge of "current" difficulty (clamping against EASY/HARD bounds is
    a separate step — see apply_difficulty_signal — so this function stays
    trivially testable in isolation).
    """
    average = (technical_score + problem_solving_score) / 2
    if average >= _DIFFICULTY_INCREASE_THRESHOLD:
        return DifficultySignal.INCREASE
    if average <= _DIFFICULTY_DECREASE_THRESHOLD:
        return DifficultySignal.DECREASE
    return DifficultySignal.MAINTAIN


def apply_difficulty_signal(current: DifficultyLevel, signal: DifficultySignal) -> DifficultyLevel:
    """Applies a signal to a current difficulty, clamped at the EASY/HARD
    boundaries (an INCREASE at HARD, or a DECREASE at EASY, is a no-op —
    matches the enum's natural ordering, never wraps around).
    """
    index = _DIFFICULTY_ORDER.index(current)
    if signal == DifficultySignal.INCREASE:
        index = min(index + 1, len(_DIFFICULTY_ORDER) - 1)
    elif signal == DifficultySignal.DECREASE:
        index = max(index - 1, 0)
    return _DIFFICULTY_ORDER[index]


# --- Coding-round boundary (Module 6 territory) --------------------------
# module §15: "For MVP: do not overcomplicate coding execution yet... do
# not fake code execution." A coding round in the plan is skipped, not
# executed and not silently dropped — RoundStatus.SKIPPED already exists
# (Module 1 baseline enum), no schema change needed.
CODING_ROUND_SKIP_REASON = (
    "Coding rounds require the Module 6 code-execution engine, not yet implemented. "
    "This round was skipped; no code was executed or faked."
)
