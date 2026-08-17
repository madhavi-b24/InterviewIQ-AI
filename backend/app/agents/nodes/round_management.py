"""Round-transition mechanics (module §14, §15) — a distinct, mechanical
concern split out from supervisor.py's FOLLOW_UP/NEXT_QUESTION/NEXT_ROUND/
COMPLETE decision: advancing round_plan position, and skipping any coding
round in the way (Module 6 territory, module §7's decision — never faked,
just cleanly skipped with a logged reason). Reads only `round_plan`,
Module 4's immutable plan snapshot surfaced via InterviewExecutionContext
— never queries interview_templates/companies/roles live (module §14's
explicit instruction: "do NOT query the live template to determine order
after the interview has started").
"""

from typing import Any, Literal

from app.agents.policy import CODING_ROUND_SKIP_REASON
from app.agents.state import InterviewState
from app.core.logging import get_logger
from app.models.enums import RoundType

logger = get_logger(__name__)


def round_transition_node(state: InterviewState) -> dict[str, Any]:
    round_plan = state["round_plan"]
    completed_index = state["current_round_index"]  # 1-based, the round just finished
    skipped: list[int] = []

    next_index = completed_index + 1
    while next_index <= len(round_plan):
        candidate = round_plan[next_index - 1]
        if candidate["round_type"] == RoundType.CODING.value:
            logger.info(
                "interview.round.skipped",
                interview_id=state["interview_id"],
                sequence_no=candidate["sequence_no"],
                reason=CODING_ROUND_SKIP_REASON,
            )
            skipped.append(candidate["sequence_no"])
            next_index += 1
            continue
        break

    if next_index > len(round_plan):
        return {"next_action": "COMPLETE", "rounds_to_skip": skipped}

    target_round = round_plan[next_index - 1]
    return {
        "current_round_index": next_index,
        "current_round": target_round["round_type"],
        "rounds_to_skip": skipped,
        # New round — fresh duplicate-avoidance/follow-up-counting scope
        # (module §17 dedup and the round-length check in supervisor.py
        # both read question_history for "this round only").
        "question_history": [],
        "answer_history": [],
        "next_action": "NEXT_QUESTION",
    }


def route_after_round_transition(state: InterviewState) -> Literal["generate_question", "complete"]:
    return "complete" if state["next_action"] == "COMPLETE" else "generate_question"


def complete_node(state: InterviewState) -> dict[str, Any]:
    return {"interview_status": "completed", "next_action": "COMPLETE", "current_question": None}
