"""Supervisor Agent (Architecture.md §5.1, module §2, §13) — owns explicit,
deterministic control flow: which node handles this turn's trigger, and
(after evaluation) what happens next. Every transition here is a plain
threshold/lookup over structured state — never an LLM's own opinion about
what should happen next (module §13's explicit instruction).
"""

from typing import Any, Literal

from app.agents.policy import DEFAULT_QUESTIONS_PER_ROUND, MAX_FOLLOW_UPS_PER_QUESTION
from app.agents.state import InterviewState
from app.models.enums import RoundType


def route_entry(
    state: InterviewState,
) -> Literal["generate_question", "select_coding_problem", "evaluate_answer", "round_transition"]:
    """Conditional-edge path function from START. Routes purely on
    `trigger` (and, for START, `current_round`'s type) — explicit, typed
    signals set by the service layer before invoking, never inferred from
    incidental state shape.

    Module 6: a plan's first round can now genuinely be CODING (Module 5's
    `_first_executable_round_index` used to skip coding rounds even as the
    starting round — that exclusion is gone, see
    app/services/interview/execution_service.py), so START itself needs
    the same round-type branch NEXT_ROUND already needs via
    route_after_round_transition. CODING_ROUND_COMPLETE always goes
    straight to round_transition — no evaluate_answer/adapt_difficulty for
    a round that was never a free-text turn.
    """
    if state["trigger"] == "CODING_ROUND_COMPLETE":
        return "round_transition"
    if state["trigger"] == "SUBMIT_ANSWER":
        return "evaluate_answer"
    return (
        "select_coding_problem"
        if state["current_round"] == RoundType.CODING.value
        else "generate_question"
    )


def decide_next_action(state: InterviewState) -> dict[str, Any]:
    """The Supervisor's core decision: FOLLOW_UP / NEXT_QUESTION /
    NEXT_ROUND / COMPLETE.
    """
    technical = state["technical_evaluation"]
    if technical is None:
        raise ValueError("decide_next_action requires technical_evaluation in state")

    if technical["follow_up_worthy"] and state["follow_up_count"] < MAX_FOLLOW_UPS_PER_QUESTION:
        return {"next_action": "FOLLOW_UP", "follow_up_count": state["follow_up_count"] + 1}

    round_type = RoundType(state["current_round"])
    target = DEFAULT_QUESTIONS_PER_ROUND.get(round_type, 1)
    # Follow-ups don't count toward round length — they deepen an existing
    # topic rather than covering new ground.
    root_questions_asked = sum(
        1 for q in state["question_history"] if q["parent_question_id"] is None
    )

    if root_questions_asked < target:
        return {"next_action": "NEXT_QUESTION", "follow_up_count": 0}

    is_last_round = state["current_round_index"] >= len(state["round_plan"])
    if is_last_round:
        return {"next_action": "COMPLETE", "follow_up_count": 0}
    return {"next_action": "NEXT_ROUND", "follow_up_count": 0}


def route_next_action(
    state: InterviewState,
) -> Literal["follow_up", "next_question", "round_transition", "complete"]:
    mapping: dict[str, Literal["follow_up", "next_question", "round_transition", "complete"]] = {
        "FOLLOW_UP": "follow_up",
        "NEXT_QUESTION": "next_question",
        "NEXT_ROUND": "round_transition",
        "COMPLETE": "complete",
    }
    next_action = state["next_action"]
    if next_action is None:
        raise ValueError("route_next_action requires next_action to be set")
    return mapping[next_action]
