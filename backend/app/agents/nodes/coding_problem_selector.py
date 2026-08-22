"""Coding Problem Selector node (Module 6, module §8/§15) — the coding
round's equivalent of question_generator.py's "produce ONE fresh,
round-opening question", except never an LLM call: which problem to
present is picked deterministically from a precomputed candidate list
(app/agents/policy.py's select_coding_problem), matching module §8's "do
not let an LLM pick the coding problem" instinct (not stated verbatim,
but the same "correctness is computed, not guessed" principle this whole
module follows — even problem SELECTION shouldn't depend on an LLM being
reliable).

DB-free, exactly like every other node (module §14) — `state["
coding_problem_candidates"]` is precomputed once per graph invocation by
InterviewExecutionService, the only layer with database access. Test case
DATA (hidden or sample) never appears in `CodingProblemCandidate` at all,
so it never reaches this node, graph state, or the LangGraph checkpointer
— see app/agents/state.py's CodingProblemCandidate docstring.
"""

from typing import Any

from app.agents.policy import select_coding_problem
from app.agents.state import InterviewState, QuestionRef


def select_coding_problem_node(state: InterviewState) -> dict[str, Any]:
    candidates = state["coding_problem_candidates"]
    excluded = set(state["coding_problem_history"])
    picked = select_coding_problem(
        candidates,
        difficulty=state["current_difficulty"],
        role_key=state.get("role_key"),
        excluded_ids=excluded,
    )
    if picked is None:
        raise ValueError(
            "select_coding_problem_node found no active coding_problems catalog entry "
            f"for difficulty={state['current_difficulty']!r} — the catalog needs at "
            "least one active problem per difficulty level for coding rounds to work."
        )

    # id is assigned once persisted — see
    # app/services/interview/execution_service.py, which is the only
    # layer with database access (mirrors question_generator_node's exact
    # same placeholder-id convention).
    question_ref: QuestionRef = {
        "id": "",
        "text": picked["description"],
        "topic": ", ".join(picked["topics"]) if picked["topics"] else picked["slug"],
        "round_type": state["current_round"],
        "difficulty": picked["difficulty"],
        "parent_question_id": None,
        "coding_problem_id": picked["id"],
    }
    return {"current_question": question_ref}
