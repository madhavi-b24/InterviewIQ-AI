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
# never an LLM-chosen graph edge). Module 6 — CODING_ROUND_COMPLETE: the
# candidate's final code submission has already been executed and graded
# by CodingRoundService (outside the graph entirely — Run/Submit are plain
# service calls, never graph turns, module §9's explicit instruction).
# This trigger only asks the graph to do the same round-advancement a
# SUBMIT_ANSWER's NEXT_ROUND path does, skipping straight to
# round_transition — no evaluate_answer/adapt_difficulty, since there is
# no free-text answer or difficulty signal for a coding round.
Trigger = Literal["START", "SUBMIT_ANSWER", "CODING_ROUND_COMPLETE"]

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
    # Module 6 — set only when round_type="coding": the selected catalog
    # problem's id (str(uuid)), so the service can copy its test cases
    # into QuestionTestCase rows at persistence time. None otherwise. Test
    # case DATA (hidden or sample) never enters graph state at all — see
    # app/agents/nodes/coding_problem_selector.py's docstring.
    coding_problem_id: str | None


class CodingProblemCandidate(TypedDict):
    """One catalog problem's selectable metadata — everything
    select_coding_problem_node needs to pick and describe a problem,
    deliberately excluding test cases (module §8: hidden tests never
    leave the service/repository layer, not even into a LangGraph
    checkpoint). Precomputed once per graph invocation by the service
    (mirrors round_plan/personalization_context — module §14's "the graph
    itself has no repository access" boundary).
    """

    id: str
    slug: str
    title: str
    description: str
    difficulty: str
    topics: list[str]
    constraints: str | None
    expected_time_complexity: str | None
    expected_space_complexity: str | None
    supported_languages: list[str]
    starter_code: dict[str, str]
    role_keys: list[str]


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
    # Module 6 — the taxonomy key (app/services/resume/role_profiles.json),
    # distinct from `role` (the display title) — select_coding_problem
    # needs this for role-priority matching, the same taxonomy Module 4's
    # catalog already keys role-specific coding_problems.role_keys on
    # (module §4's "one taxonomy, not two" rule). None for a role with no
    # matching taxonomy entry — generic catalog problems still apply.
    role_key: str | None
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

    # --- Grounding text assembled once per turn by the (deterministic)
    # Knowledge Agent, fed into whichever LLM call needs it this turn.
    knowledge_context: str

    # --- Module 6: coding-round selection. Every active catalog problem
    # (small — module §8's "small, high-quality catalog"), precomputed by
    # the service so select_coding_problem_node stays DB-free like every
    # other node (module §14). Filtered/picked deterministically at node
    # execution time against whatever current_round/current_difficulty/
    # role_key turn out to be *after* this turn's own adaptation — see
    # app/agents/policy.py's select_coding_problem.
    coding_problem_candidates: list[CodingProblemCandidate]
    # Catalog problem ids already asked anywhere in THIS interview (not
    # reset per round, unlike question_history) — best-effort repeat
    # avoidance across multiple coding rounds in one plan (module §8).
    coding_problem_history: list[str]
