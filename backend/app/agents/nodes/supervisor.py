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


def route_entry(state: InterviewState) -> Literal["generate_question", "evaluate_answer"]:
    """Conditional-edge path function from START. Routes purely on
    `trigger`, set by the service layer before invoking — an explicit,
    typed signal, never inferred from state shape.
    """
    return "generate_question" if state["trigger"] == "START" else "evaluate_answer"


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
