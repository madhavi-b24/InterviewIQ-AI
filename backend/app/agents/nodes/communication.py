"""Communication Agent (Architecture.md §5.1, module §11) — observable
communication qualities only (clarity, structure, conciseness,
terminology, ability to explain reasoning). Deliberately independent of
technical correctness — given no evaluation/difficulty context, only the
raw question/answer text. Never infers personality, mental state, gender,
or confidence as a psychological trait (module §9, §11) — see
app/services/interview_intelligence/schemas.py's CommunicationEvaluation
docstring for exactly how "confidence" is redefined to stay observable.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.state import CommunicationEvaluationState, InterviewState
from app.services.interview_intelligence.provider import InterviewAgentProvider


def make_communication_node(
    provider: InterviewAgentProvider,
) -> Callable[[InterviewState], Awaitable[dict[str, Any]]]:
    async def communication_node(state: InterviewState) -> dict[str, Any]:
        question = state["last_question"]
        answer = state["last_answer"]
        if question is None or answer is None:
            raise ValueError("communication_node requires last_question/last_answer in state")

        result = await provider.evaluate_communication(
            question_text=question["text"], answer_text=answer["text"]
        )
        communication: CommunicationEvaluationState = {
            "communication_score": result.communication_score,
            "communication_explanation": result.communication_explanation,
            "confidence_score": result.confidence_score,
            "confidence_explanation": result.confidence_explanation,
        }
        return {"communication_evaluation": communication}

    return communication_node
