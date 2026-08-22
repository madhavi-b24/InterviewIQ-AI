"""Module 5/6's deterministic execution policy — every tunable constant and
non-LLM decision rule the interview graph depends on, in one reviewable
place. Nothing in this file calls Gemini; that's the point (module §12,
§13: "do NOT let an LLM freely decide the difficulty," "use explicit
transition rules... avoid letting an LLM return arbitrary graph
transitions").
"""

from typing import TYPE_CHECKING

from app.models.enums import DifficultyLevel, DifficultySignal, RoundType

if TYPE_CHECKING:
    from app.agents.state import CodingProblemCandidate

# --- Round length -----------------------------------------------------------
# Module 4's `template_rounds` schema (approved, not reopened here) has no
# "target question count" column — round length is therefore an execution
# -engine POLICY, not a plan attribute. One place to tune it. A coding
# round always presents exactly one problem (module §8/§15's "1 problem
# per round" — Run/Submit attempts on that one problem are unbounded, but
# the round itself never advances to a second problem).
DEFAULT_QUESTIONS_PER_ROUND: dict[RoundType, int] = {
    RoundType.INTRODUCTION: 1,
    RoundType.TECHNICAL: 3,
    RoundType.CODING: 1,
    RoundType.BEHAVIORAL: 2,
    RoundType.RESUME_DISCUSSION: 2,
    RoundType.SYSTEM_DESIGN: 2,
    RoundType.FINAL: 1,
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


# --- Coding-round problem selection (Module 6) -----------------------------
# Deterministic, pure — no DB access (module §14: nodes stay DB-free),
# called by app/agents/nodes/coding_problem_selector.py against the small
# candidate list the service precomputed. Mirrors compute_difficulty_signal
# above: score/pick in, no side effects, independently testable.


def select_coding_problem(
    candidates: list["CodingProblemCandidate"],
    *,
    difficulty: str,
    role_key: str | None,
    excluded_ids: set[str],
) -> "CodingProblemCandidate | None":
    """Picks exactly one problem for a coding round about to start.

    Priority, in order: (1) matches `difficulty` exactly — a catalog
    problem's difficulty is never substituted with a "close enough" one;
    (2) prefers a problem not already asked anywhere else in this
    interview (`excluded_ids`), but falls back to allowing a repeat rather
    than failing the round outright if the catalog has nothing else at
    this difficulty; (3) prefers a `role_key`-specific problem over a
    generic one, never narrowing to zero candidates if only generic ones
    exist. `candidates` is expected pre-sorted (by slug, matching
    CodingProblemRepository's query order) so the final tie-break — the
    first remaining candidate — is deterministic and stable across calls,
    not incidentally dependent on dict/set iteration order.

    Returns None only if the catalog has no active problem at all for
    `difficulty` — a catalog configuration gap, not a normal runtime
    state; the caller (the node) treats that as an error, never silently
    substituting a different difficulty.
    """
    by_difficulty = [c for c in candidates if c["difficulty"] == difficulty]
    if not by_difficulty:
        return None

    unused = [c for c in by_difficulty if c["id"] not in excluded_ids]
    pool = unused or by_difficulty

    if role_key:
        role_matched = [c for c in pool if role_key in c["role_keys"]]
        if role_matched:
            return role_matched[0]
    generic = [c for c in pool if not c["role_keys"]]
    return (generic or pool)[0]


# --- Coding-evaluation aggregate score (Module 6) ---------------------------
# `coding_evaluations.overall_code_score` is a deterministic weighted
# combination of the sub-scores, not an LLM-set number (module §11: "do
# not let the model freely decide the headline number" — the same reason
# adapt_difficulty above is deterministic). correctness dominates the
# weighting (a beautifully written wrong answer is still wrong) while the
# LLM-judged qualities fill out the rest.
CODE_SCORE_WEIGHTS: dict[str, float] = {
    "correctness": 0.40,
    "readability": 0.15,
    "optimization": 0.20,
    "edge_case": 0.15,
    # code_quality_score/complexity_score in module §11's requested field
    # list are covered by readability_score/time_complexity+space_complexity
    # respectively (see app/services/code_evaluation/schemas.py's
    # docstring) rather than duplicated as separate weighted terms.
    "quality": 0.10,
}


def compute_overall_code_score(
    *,
    correctness_score: float,
    readability_score: float,
    optimization_score: float,
    edge_case_score: float,
) -> float:
    """Pure weighted average, 0-100. `quality` reuses readability_score —
    module §11's `code_quality_score` and CodeEvaluationResult's
    `readability_score` are the same concept (structure/naming/clarity),
    not two independent LLM judgments of the same code — see
    app/services/code_evaluation/schemas.py's docstring for why that
    field wasn't duplicated.
    """
    weights = CODE_SCORE_WEIGHTS
    total = (
        correctness_score * weights["correctness"]
        + readability_score * weights["readability"]
        + optimization_score * weights["optimization"]
        + edge_case_score * weights["edge_case"]
        + readability_score * weights["quality"]
    )
    return round(total, 2)
