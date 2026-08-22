"""Interview Agent (Architecture.md §5.1, module §8) — manages
conversational flow within a round: specifically, generates a follow-up
question grounded in the *specific reason* the Evaluation Agent flagged
(TechnicalEvaluation.follow_up_reason), never a generic "tell me more."
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.nodes import knowledge
from app.agents.state import InterviewState, QuestionRef
from app.services.interview_intelligence.provider import InterviewAgentProvider


def make_interview_agent_node(
    provider: InterviewAgentProvider,
) -> Callable[[InterviewState], Awaitable[dict[str, Any]]]:
    async def interview_agent_node(state: InterviewState) -> dict[str, Any]:
        last_question = state["last_question"]
        last_answer = state["last_answer"]
        technical = state["technical_evaluation"]
        if last_question is None or last_answer is None:
            raise ValueError("interview_agent_node requires last_question/last_answer in state")

        reason = (
            technical["follow_up_reason"]
            if technical and technical["follow_up_reason"]
            else "the answer could use more depth"
        )
        knowledge_context = knowledge.retrieve(
            topic=last_question["topic"],
            role_key=None,
            personalization=state.get("personalization_context"),
        )

        result = await provider.generate_follow_up(
            role_title=state["role"],
            round_type=state["current_round"],
            difficulty=state["current_difficulty"],
            previous_question=last_question["text"],
            previous_answer=last_answer["text"],
            follow_up_reason=reason,
            knowledge_context=knowledge_context,
        )

        question_ref: QuestionRef = {
            "id": "",
            "text": result.question_text,
            "topic": result.topic,
            "round_type": state["current_round"],
            "difficulty": state["current_difficulty"],
            "parent_question_id": last_question["id"],
            "coding_problem_id": None,  # follow-ups never target coding rounds (module §8)
        }
        return {"current_question": question_ref}

    return interview_agent_node
