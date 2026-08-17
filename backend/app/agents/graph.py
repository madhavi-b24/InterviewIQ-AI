"""Interview LangGraph assembly — Architecture.md §5 (Module 5).

`build_interview_graph(provider, checkpointer)` compiles a fresh
`StateGraph(InterviewState)` per call — node closures capture `provider`
so no node needs its own dependency-injection mechanism, and
`checkpointer` is baked in via `.compile(checkpointer=...)`, exactly
LangGraph's own API (verified directly against the installed
langgraph==0.2.76 before writing this: `StateGraph.compile(checkpointer:
BaseCheckpointSaver | bool | None = None, ...)`). Called once per turn
from app/services/interview/execution_service.py, inside the
app/agents/checkpointer.py context manager — see that service for why
compiling per-turn (not once at import time) is the right call here: the
checkpointer's underlying connection is opened/closed per turn by that
existing scaffold, so the compiled graph's lifetime matches it.

Graph shape (module §2: explicit nodes, no giant single node):

    START --(route_entry: trigger)-->
        "START"          -> generate_question -> END
        "SUBMIT_ANSWER"  -> evaluate_answer -> evaluate_communication -> adapt_difficulty
                             -> decide_next_action --(route_next_action)-->
                                 FOLLOW_UP     -> follow_up -> END
                                 NEXT_QUESTION -> generate_question -> END
                                 COMPLETE      -> complete -> END
                                 NEXT_ROUND    -> round_transition
                                     --(route_after_round_transition)-->
                                         "generate_question" -> generate_question -> END
                                         "complete"          -> complete -> END

Knowledge Agent (Architecture.md §5.1, module §10) is deliberately not a
separate node — see app/agents/nodes/knowledge.py's docstring for why; for
MVP it's a deterministic helper called inline by whichever node needs
grounding context, not an LLM call and not its own graph step.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.nodes.communication import make_communication_node
from app.agents.nodes.difficulty import difficulty_node
from app.agents.nodes.evaluation import make_evaluation_node
from app.agents.nodes.interview_agent import make_interview_agent_node
from app.agents.nodes.question_generator import make_question_generator_node
from app.agents.nodes.round_management import (
    complete_node,
    round_transition_node,
    route_after_round_transition,
)
from app.agents.nodes.supervisor import decide_next_action, route_entry, route_next_action
from app.agents.state import InterviewState
from app.services.interview_intelligence.provider import InterviewAgentProvider


def build_interview_graph(
    provider: InterviewAgentProvider, checkpointer: BaseCheckpointSaver
) -> CompiledStateGraph:
    graph: StateGraph = StateGraph(InterviewState)

    graph.add_node("generate_question", make_question_generator_node(provider))
    graph.add_node("follow_up", make_interview_agent_node(provider))
    graph.add_node("evaluate_answer", make_evaluation_node(provider))
    graph.add_node("evaluate_communication", make_communication_node(provider))
    graph.add_node("adapt_difficulty", difficulty_node)
    graph.add_node("decide_next_action", decide_next_action)
    graph.add_node("round_transition", round_transition_node)
    graph.add_node("complete", complete_node)

    graph.add_conditional_edges(
        START,
        route_entry,
        {"generate_question": "generate_question", "evaluate_answer": "evaluate_answer"},
    )
    graph.add_edge("evaluate_answer", "evaluate_communication")
    graph.add_edge("evaluate_communication", "adapt_difficulty")
    graph.add_edge("adapt_difficulty", "decide_next_action")
    graph.add_conditional_edges(
        "decide_next_action",
        route_next_action,
        {
            "follow_up": "follow_up",
            "next_question": "generate_question",
            "round_transition": "round_transition",
            "complete": "complete",
        },
    )
    graph.add_conditional_edges(
        "round_transition",
        route_after_round_transition,
        {"generate_question": "generate_question", "complete": "complete"},
    )
    graph.add_edge("generate_question", END)
    graph.add_edge("follow_up", END)
    graph.add_edge("complete", END)

    return graph.compile(checkpointer=checkpointer)
