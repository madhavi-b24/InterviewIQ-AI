"""Difficulty Agent (Architecture.md §5.1, module §12) — pure deterministic
Python, zero LLM calls (see app/agents/policy.py for the actual threshold
policy this node applies). Also finalizes this turn's merged evaluation
summary and running score aggregates, since both are a direct, cheap
function of the two evaluation results this node already has in hand — a
separate "merge" node would only add graph-routing overhead for no
behavioral benefit.
"""

from typing import Any

from app.agents.policy import apply_difficulty_signal, compute_difficulty_signal
from app.agents.state import InterviewState
from app.models.enums import DifficultyLevel


def _running_average(previous_average: float, previous_count: int, new_value: float) -> float:
    if previous_count == 0:
        return new_value
    return ((previous_average * previous_count) + new_value) / (previous_count + 1)


def difficulty_node(state: InterviewState) -> dict[str, Any]:
    technical = state["technical_evaluation"]
    communication = state["communication_evaluation"]
    if technical is None or communication is None:
        raise ValueError("difficulty_node requires both evaluations in state")

    signal = compute_difficulty_signal(
        technical_score=technical["technical_score"],
        problem_solving_score=technical["problem_solving_score"],
    )
    new_difficulty = apply_difficulty_signal(DifficultyLevel(state["current_difficulty"]), signal)

    evaluation = {
        "technical": {
            "score": technical["technical_score"],
            "explanation": technical["technical_explanation"],
        },
        "problem_solving": {
            "score": technical["problem_solving_score"],
            "explanation": technical["problem_solving_explanation"],
        },
        "communication": {
            "score": communication["communication_score"],
            "explanation": communication["communication_explanation"],
        },
        "confidence": {
            "score": communication["confidence_score"],
            "explanation": communication["confidence_explanation"],
        },
        "difficulty_signal": signal.value,
    }

    scores = state["interview_scores"]
    prior_count = scores["answered_count"]
    new_scores = {
        "technical": _running_average(
            scores["technical"], prior_count, technical["technical_score"]
        ),
        "problem_solving": _running_average(
            scores["problem_solving"], prior_count, technical["problem_solving_score"]
        ),
        "communication": _running_average(
            scores["communication"], prior_count, communication["communication_score"]
        ),
        "confidence": _running_average(
            scores["confidence"], prior_count, communication["confidence_score"]
        ),
        "answered_count": prior_count + 1,
    }
    # This answer's combined score — a lightweight, non-authoritative
    # display figure. The final report's per-section scoring is Module 7's
    # job, computed from persisted answer_evaluations rows, not this field.
    this_answer_score = (
        technical["technical_score"]
        + technical["problem_solving_score"]
        + communication["communication_score"]
        + communication["confidence_score"]
    ) / 4

    return {
        "previous_difficulty": state["current_difficulty"],
        "current_difficulty": new_difficulty.value,
        "evaluation": evaluation,
        "interview_scores": new_scores,
        "round_score": this_answer_score,
    }
