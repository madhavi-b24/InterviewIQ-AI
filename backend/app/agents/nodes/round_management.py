"""Round-transition mechanics (module §14) — a distinct, mechanical
concern split out from supervisor.py's FOLLOW_UP/NEXT_QUESTION/NEXT_ROUND/
COMPLETE decision: advancing round_plan position by exactly one. Reads
only `round_plan`, Module 4's immutable plan snapshot surfaced via
InterviewExecutionContext — never queries interview_templates/companies/
roles live (module §14's explicit instruction: "do NOT query the live
template to determine order after the interview has started").

Module 6 note: this node no longer skips coding rounds — Module 5 had it
unconditionally skip every RoundType.CODING round (logged as
CODING_ROUND_SKIP_REASON, "not yet implemented"); now that coding rounds
execute for real (app/agents/nodes/coding_problem_selector.py,
CodingRoundService), that placeholder branch is gone, not merely
disabled. route_after_round_transition routes a coding round to
select_coding_problem instead of generate_question — the only change on
this side of the boundary.
"""

from typing import Any, Literal

from app.agents.state import InterviewState
from app.models.enums import RoundType


def round_transition_node(state: InterviewState) -> dict[str, Any]:
    round_plan = state["round_plan"]
    completed_index = state["current_round_index"]  # 1-based, the round just finished
    next_index = completed_index + 1

    if next_index > len(round_plan):
        return {"next_action": "COMPLETE"}

    target_round = round_plan[next_index - 1]
    return {
        "current_round_index": next_index,
        "current_round": target_round["round_type"],
        # New round — fresh duplicate-avoidance/follow-up-counting scope
        # (module §17 dedup and the round-length check in supervisor.py
        # both read question_history for "this round only"; coding_problem_
        # history is deliberately NOT reset here — module §8's whole-
        # interview repeat avoidance spans rounds, see state.py).
        "question_history": [],
        "answer_history": [],
        "next_action": "NEXT_QUESTION",
    }


def route_after_round_transition(
    state: InterviewState,
) -> Literal["generate_question", "select_coding_problem", "complete"]:
    if state["next_action"] == "COMPLETE":
        return "complete"
    return (
        "select_coding_problem"
        if state["current_round"] == RoundType.CODING.value
        else "generate_question"
    )


def complete_node(state: InterviewState) -> dict[str, Any]:
    return {"interview_status": "completed", "next_action": "COMPLETE", "current_question": None}
