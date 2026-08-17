"""Shared LangGraph state shape — Architecture.md §5.2 (Module 5).

This is the graph's TRANSIENT execution state — the minimum working memory
one turn's node sequence needs to pass to each other. It is NOT the
durable record of the interview: Postgres (interview_sessions,
interview_rounds, questions, answers, answer_evaluations) is (module §4).
Every field below is rebuilt fresh from Postgres + InterviewExecutionContext
at the start of every graph invocation (see
app/services/interview/execution_service.py) — nothing here is trusted
blindly from a stale checkpoint for a durable fact. LangGraph's own
Postgres checkpointer (app/agents/checkpointer.py) still runs underneath
this for mid-turn crash recovery, but this state is not itself the
system's recoverability guarantee — Postgres is.

No secrets, no full resume text, and no raw PII beyond what
InterviewExecutionContext.personalization already exposes (evidence
snippets, not the resume document itself) ever belongs here.
"""

from typing import Any, Literal, TypedDict

# What kind of turn this graph invocation is processing — drives the
# Supervisor's routing (module §2/§13: explicit, deterministic transitions,
# never an LLM-chosen graph edge).
Trigger = Literal["START", "SUBMIT_ANSWER"]

# The Supervisor's deterministic post-evaluation decision (module §13).
NextAction = Literal["FOLLOW_UP", "NEXT_QUESTION", "NEXT_ROUND", "COMPLETE"]


class QuestionRef(TypedDict):
    """A lightweight pointer to a question — id + just enough text to
    prompt/display with, never the full ORM row (avoids duplicating
    documents into graph state, module §3's explicit instruction).
    """

    id: str
    text: str
    topic: str
    round_type: str
    difficulty: str
    parent_question_id: str | None


class AnswerRef(TypedDict):
    id: str
    question_id: str
    text: str


class TechnicalEvaluationState(TypedDict):
    """Evaluation Agent's output for the answer currently in flight — lives
    in state only long enough for the Difficulty Agent and the next-action
    router to read it this turn; the durable copy is
    answer_evaluations (Database.md §6).
    """

    technical_score: float
    technical_explanation: str
    problem_solving_score: float
    problem_solving_explanation: str
    follow_up_worthy: bool
    follow_up_reason: str | None


class CommunicationEvaluationState(TypedDict):
    communication_score: float
    communication_explanation: str
    confidence_score: float
    confidence_explanation: str


class InterviewScores(TypedDict):
    """Running per-dimension averages across the interview so far — a
    small aggregate for display/context only, never the source of truth
    for the final report (Module 7's job, computed from persisted
    answer_evaluations rows, not from this cache).
    """

    technical: float
    problem_solving: float
    communication: float
    confidence: float
    answered_count: int


class PersonalizationContextState(TypedDict):
    """Flattened, primitive form of Module 4's PersonalizationContext —
    exactly what interview_intelligence's primitive-only provider methods
    need (app/services/interview_intelligence/provider.py), so graph nodes
    never import Module 4's Pydantic types directly.
    """

    skills: list[str]
    focus_areas: list[str]
    project_titles: list[str]
    evidence_snippets: list[str]


class InterviewState(TypedDict):
    # --- Identity / ownership — who and what this turn is for.
    interview_id: str
    user_id: str

    # --- Plan context, read-only for this graph (module §14: "do NOT
    # query the live template after the interview has started" — this
    # comes from Module 4's immutable plan_snapshot via
    # InterviewExecutionContext, never a fresh companies/roles/templates
    # query).
    company: str | None
    role: str
    mode: str
    round_plan: list[dict[str, Any]]  # ordered RoundExecutionPlan-shaped dicts

    # --- Where the interview is right now.
    current_round: str  # RoundType.value of the active round
    current_round_index: int  # 1-based sequence_no, matches interview_rounds.sequence_no
    current_question: QuestionRef | None
    current_difficulty: str  # DifficultyLevel.value — the *dynamic* value (module §12)
    # Value just before this turn's adaptation, so a response can show the
    # transition without a second Postgres read.
    previous_difficulty: str

    # --- This turn's working memory — NOT full interview history (that
    # lives in Postgres). Scoped to the current round only, since that's
    # all duplicate-avoidance (module §17) and follow-up counting need.
    last_question: QuestionRef | None
    last_answer: AnswerRef | None
    question_history: list[QuestionRef]
    answer_history: list[AnswerRef]

    # --- Evaluation results for the answer currently being processed.
    technical_evaluation: TechnicalEvaluationState | None
    communication_evaluation: CommunicationEvaluationState | None
    evaluation: dict[str, Any] | None  # merged view of both, shaped for the API response

    # --- Follow-up bookkeeping (module §8). Follow-ups asked for the
    # current root question, capped by policy.MAX_FOLLOW_UPS_PER_QUESTION.
    follow_up_count: int

    # --- Aggregate scoring, display/context only.
    round_score: float | None
    interview_scores: InterviewScores

    # --- Resume grounding (module §16) — primitives only, never raw text.
    personalization_context: PersonalizationContextState | None
    resume_evidence_context: list[
        str
    ]  # the evidence snippets actually offered to the LLM this turn

    # --- Control flow — deterministic, never LLM-decided (module §13).
    trigger: Trigger
    next_action: NextAction | None
    interview_status: str  # SessionStatus.value this turn is about to make durable
    # sequence_no's the round-transition step jumped over this turn (coding
    # rounds, module §15) — the service persists these as
    # InterviewRound.status=SKIPPED.
    rounds_to_skip: list[int]

    # --- Grounding text assembled once per turn by the (deterministic)
    # Knowledge Agent, fed into whichever LLM call needs it this turn.
    knowledge_context: str
