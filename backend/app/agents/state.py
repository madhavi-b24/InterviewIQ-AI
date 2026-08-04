"""Shared LangGraph state shape — Architecture.md §5.2.

Field shapes only. No node populates these yet; the agent graph itself
is built in Module 5 (Core Interview Engine).
"""

from typing import Any, TypedDict


class ResumeContext(TypedDict):
    skills: list[str]
    projects: list[str]
    gaps: list[str]


class RunningScores(TypedDict):
    technical: float
    coding: float
    communication: float
    problem_solving: float
    confidence: float


class InterviewState(TypedDict):
    session_id: str
    user_id: str
    resume_context: ResumeContext
    company: str | None
    role: str
    current_round: str
    current_difficulty: str
    conversation_history: list[dict[str, Any]]
    last_question: dict[str, Any] | None
    last_answer: dict[str, Any] | None
    running_scores: RunningScores
    round_plan: list[str]
