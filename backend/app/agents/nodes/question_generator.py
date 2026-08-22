"""Question Generator Agent (Architecture.md §5.1, module §7) — produces
ONE fresh, round-opening question. Never a follow-up (that's
interview_agent.py) and never a list of questions.
"""

import re
from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.nodes import knowledge
from app.agents.state import InterviewState, QuestionRef
from app.services.interview_intelligence.provider import InterviewAgentProvider


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def make_question_generator_node(
    provider: InterviewAgentProvider,
) -> Callable[[InterviewState], Awaitable[dict[str, Any]]]:
    async def question_generator_node(state: InterviewState) -> dict[str, Any]:
        personalization = state.get("personalization_context")
        skills = personalization["skills"] if personalization else []
        evidence = personalization["evidence_snippets"] if personalization else []
        asked_texts = [q["text"] for q in state["question_history"]]
        already_asked_normalized = {_normalize(t) for t in asked_texts}

        knowledge_context = knowledge.retrieve(
            topic=None, role_key=None, personalization=personalization
        )

        result = await provider.generate_question(
            role_title=state["role"],
            round_type=state["current_round"],
            difficulty=state["current_difficulty"],
            skills=skills,
            evidence_snippets=evidence,
            asked_questions=asked_texts,
            knowledge_context=knowledge_context,
        )

        # Deterministic duplicate control (module §17) — one bounded retry,
        # then proceed regardless. No semantic-similarity infra for MVP.
        if _normalize(result.question_text) in already_asked_normalized:
            result = await provider.generate_question(
                role_title=state["role"],
                round_type=state["current_round"],
                difficulty=state["current_difficulty"],
                skills=skills,
                evidence_snippets=evidence,
                asked_questions=[*asked_texts, result.question_text],
                knowledge_context=knowledge_context,
            )

        # id is assigned once persisted — see
        # app/services/interview/execution_service.py, which is the only
        # layer with database access.
        question_ref: QuestionRef = {
            "id": "",
            "text": result.question_text,
            "topic": result.topic,
            "round_type": state["current_round"],
            "difficulty": state["current_difficulty"],
            "parent_question_id": None,
            "coding_problem_id": None,  # this node never handles coding rounds (module §8)
        }
        return {"current_question": question_ref, "resume_evidence_context": evidence}

    return question_generator_node
