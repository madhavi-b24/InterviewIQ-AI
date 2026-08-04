"""Interview LangGraph assembly — Architecture.md §5.

Not implemented yet. The Supervisor, Question Generator, Knowledge,
Interview, Evaluation, Communication, Difficulty, Learning, and Report
agents (Architecture.md §5.1) are all Module 5+ work. This stub exists so
the import path and function signature are stable for services that will
depend on it.
"""

from langgraph.graph import StateGraph

# Will be StateGraph(InterviewState) once nodes exist — see app/agents/state.py.


def build_interview_graph() -> StateGraph:
    raise NotImplementedError(
        "Interview agent graph is scaffolded but not implemented — see Roadmap.md Module 5"
    )
