"""Evaluation Agent (Architecture.md §5.1, module §9) — technical
correctness and problem-solving only. Coding correctness/readability/
optimization are Module 6's CodingEvaluation (out of scope here).
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.nodes import knowledge
from app.agents.state import InterviewState, TechnicalEvaluationState
from app.services.interview_intelligence.provider import InterviewAgentProvider


def make_evaluation_node(
    provider: InterviewAgentProvider,
) -> Callable[[InterviewState], Awaitable[dict[str, Any]]]:
    async def evaluation_node(state: InterviewState) -> dict[str, Any]:
        question = state["last_question"]
        answer = state["last_answer"]
        if question is None or answer is None:
            raise ValueError("evaluation_node requires last_question/last_answer in state")

        knowledge_context = knowledge.retrieve(
            topic=question["topic"],
            role_key=None,
            personalization=state.get("personalization_context"),
        )

        result = await provider.evaluate_technical(
            question_text=question["text"],
            answer_text=answer["text"],
            round_type=state["current_round"],
            difficulty=state["current_difficulty"],
            knowledge_context=knowledge_context,
        )
        technical: TechnicalEvaluationState = {
            "technical_score": result.technical_score,
            "technical_explanation": result.technical_explanation,
            "problem_solving_score": result.problem_solving_score,
            "problem_solving_explanation": result.problem_solving_explanation,
            "follow_up_worthy": result.follow_up_worthy,
            "follow_up_reason": result.follow_up_reason,
        }
        return {"technical_evaluation": technical}

    return evaluation_node
