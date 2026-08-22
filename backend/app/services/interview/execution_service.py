"""InterviewExecutionService — the Module 5 use case: execute an
already-planned, immutable interview via the LangGraph engine.

Mirrors InterviewPlannerService's shape (app/services/planning/interview_planner.py):
constructor takes only `AsyncSession`, builds its own repositories, routers
call exactly these methods, no SQLAlchemy/graph-building logic in the
router. The only caller of build_interview_graph() — no other layer
touches the graph directly.

Transaction/locking design (module §5, §22 — idempotency, no duplicate
turns, no corrupted state on LLM failure):
  - `submit_answer` is deliberately two-phase. Phase 1 persists the
    candidate's Answer row and COMMITS it immediately, before any LLM
    call — the candidate's submission survives even if the graph
    invocation that follows fails (module §22: "preserve the candidate's
    submitted answer"). This necessarily releases the session's row lock
    for a moment; the `answers.question_id` unique constraint is the
    backstop against a genuine concurrent duplicate in that window (caught
    and translated to a clean 409, never a raw IntegrityError). Phase 2
    re-acquires the row lock and does everything else (evaluate, adapt
    difficulty, decide next action, persist results) in one final commit.
  - Idempotency is keyed on whether an AnswerEvaluation already exists for
    the answer: if yes, replay the persisted result (zero new LLM calls,
    zero new rows); if an Answer exists with no evaluation yet (a prior
    attempt died mid-turn), reuse it and evaluate from the already-
    persisted text rather than erroring or duplicating.
  - `start_interview` doesn't need the two-phase split: if it fails,
    nothing has been persisted yet (no candidate data to lose), so a
    retry is simply "try /start again."
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.checkpointer import get_checkpointer
from app.agents.graph import build_interview_graph
from app.agents.state import (
    AnswerRef,
    CodingProblemCandidate,
    InterviewScores,
    InterviewState,
    PersonalizationContextState,
    QuestionRef,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from app.core.logging import get_logger
from app.models.coding import CodingProblem
from app.models.enums import (
    DifficultyLevel,
    DifficultySignal,
    QuestionSource,
    QuestionType,
    RoundStatus,
    RoundType,
    SessionStatus,
)
from app.models.evaluation import AnswerEvaluation
from app.models.interview import (
    Answer,
    InterviewRound,
    InterviewSession,
    Question,
    QuestionTestCase,
)
from app.repositories.coding import CodingProblemRepository
from app.repositories.evaluation import AnswerEvaluationRepository
from app.repositories.interview import (
    AnswerRepository,
    InterviewRoundRepository,
    InterviewSessionRepository,
    QuestionRepository,
)
from app.services.interview.execution_context import (
    PersonalizationContext,
    RoundExecutionPlan,
    build_execution_context,
)
from app.services.interview_intelligence.provider import (
    InterviewAgentProvider,
    InterviewIntelligenceProviderError,
    InterviewIntelligenceTimeoutError,
)

logger = get_logger(__name__)


class InterviewExecutionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._interviews = InterviewSessionRepository(session)
        self._rounds = InterviewRoundRepository(session)
        self._questions = QuestionRepository(session)
        self._answers = AnswerRepository(session)
        self._evaluations = AnswerEvaluationRepository(session)
        self._coding_problems = CodingProblemRepository(session)

    # --- Reads ---------------------------------------------------------------

    async def get_owned(self, interview_id: uuid.UUID, user_id: uuid.UUID) -> InterviewSession:
        interview = await self._interviews.get_owned(interview_id, user_id)
        if interview is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")
        return interview

    async def get_current_turn(
        self, interview_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[InterviewSession, Question | None]:
        """Pure Postgres read, no graph invocation — module §6's "come back
        later without losing the interview" requirement, with zero LLM cost.
        """
        interview = await self.get_owned(interview_id, user_id)
        question = None
        if interview.current_question_id is not None:
            question = await self._questions.get_with_round(interview.current_question_id)
        return interview, question

    # --- Start -----------------------------------------------------------------

    async def start_interview(
        self, *, interview_id: uuid.UUID, user_id: uuid.UUID, provider: InterviewAgentProvider
    ) -> tuple[InterviewSession, Question]:
        interview = await self._interviews.get_owned_for_update(interview_id, user_id)
        if interview is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")
        if interview.status != SessionStatus.NOT_STARTED:
            raise ConflictError(
                "interview has already been started", code="INTERVIEW_ALREADY_STARTED"
            )

        context = build_execution_context(interview)
        first_index = _first_executable_round_index(context.rounds)
        if first_index is None:
            raise UnprocessableEntityError(
                "this interview's plan has no rounds — nothing to execute",
                code="EMPTY_ROUND_PLAN",
            )

        round_ = await self._rounds.get_by_sequence(interview.id, first_index)
        if round_ is None:
            raise UnprocessableEntityError(
                "interview plan is missing its first round", code="ROUND_NOT_FOUND"
            )
        for plan_round in context.rounds:
            if plan_round.sequence_no < first_index:
                leading = await self._rounds.get_by_sequence(interview.id, plan_round.sequence_no)
                if leading is not None:
                    await self._rounds.mark_status(leading, RoundStatus.SKIPPED)

        personalization_state = _personalization_to_state(context.personalization)
        coding_candidates = await self._coding_candidates()
        state: InterviewState = {
            "interview_id": str(interview.id),
            "user_id": str(user_id),
            "company": context.company_name,
            "role": context.role_title,
            "role_key": context.role_key,
            "mode": context.mode.value,
            "round_plan": [_round_plan_to_dict(r) for r in context.rounds],
            "current_round": round_.round_type.value,
            "current_round_index": first_index,
            "current_question": None,
            "current_difficulty": interview.starting_difficulty.value,
            "previous_difficulty": interview.starting_difficulty.value,
            "last_question": None,
            "last_answer": None,
            "question_history": [],
            "answer_history": [],
            "technical_evaluation": None,
            "communication_evaluation": None,
            "evaluation": None,
            "follow_up_count": 0,
            "round_score": None,
            "interview_scores": _empty_scores(),
            "personalization_context": personalization_state,
            "resume_evidence_context": [],
            "trigger": "START",
            "next_action": None,
            "interview_status": interview.status.value,
            "knowledge_context": "",
            "coding_problem_candidates": coding_candidates,
            "coding_problem_history": [],  # nothing asked yet — this is the first round
        }

        thread_id = f"interview:{interview.id}:{uuid.uuid4().hex}"
        result = await self._invoke_graph(provider, thread_id, state)

        now = datetime.now(UTC)
        await self._rounds.mark_status(round_, RoundStatus.ACTIVE, started_at=now)
        question = await self._persist_question(result, round_)

        interview.status = SessionStatus.IN_PROGRESS
        interview.started_at = now
        interview.current_round_sequence = first_index
        interview.current_question_id = question.id
        interview.langgraph_thread_id = thread_id

        await self._session.commit()
        await self._session.refresh(interview, attribute_names=["rounds"])
        logger.info(
            "interview.started",
            interview_id=str(interview.id),
            user_id=str(user_id),
            round=round_.round_type.value,
        )
        return interview, question

    # --- Answers ---------------------------------------------------------------

    async def submit_answer(
        self,
        *,
        interview_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        answer_text: str,
        provider: InterviewAgentProvider,
    ) -> tuple[InterviewSession, dict, DifficultyLevel, Question | None]:
        """Returns (interview, evaluation_dict, previous_difficulty,
        next_question) — next_question is None once the interview has
        completed. The router shapes these into AnswerResponseOut.

        Idempotency check runs BEFORE the "is this the current question"
        check, deliberately — an already-answered-and-evaluated question is
        always replayed, regardless of whether the interview has since
        moved on to a later question or even completed. Getting this
        ordering backwards was a real bug caught by this module's own test
        suite (test_duplicate_answer_retry_is_idempotent): checking
        "is this the current question" first rejected a legitimate replay
        of the *previous* turn as 409 STALE_QUESTION_ID the moment that
        turn had already advanced the interview to a new question — which
        defeated the whole point of the idempotency check for the single
        most common retry shape (client resubmits promptly after a lost
        response). Known simplification: a replay's `previous_difficulty`
        and `next_question` reflect the interview's state *now*, not
        necessarily the exact values from the original turn, if further
        turns happened in between — acceptable for the realistic case
        (prompt retry, nothing else happened since), not attempted for the
        pathological case (retrying a turn from several turns ago).
        """
        interview = await self._interviews.get_owned_for_update(interview_id, user_id)
        if interview is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")

        question = await self._questions.get_by_id(question_id)
        if question is None:
            raise NotFoundError("question not found", code="QUESTION_NOT_FOUND")

        answer = await self._answers.get_by_question_id(question_id)
        if answer is not None:
            existing_eval = await self._evaluations.get_by_answer_id(answer.id)
            if existing_eval is not None:
                logger.info(
                    "interview.answer.idempotent_replay",
                    interview_id=str(interview_id),
                    question_id=str(question_id),
                )
                next_question = (
                    await self._questions.get_with_round(interview.current_question_id)
                    if interview.current_question_id
                    else None
                )
                return (
                    interview,
                    _evaluation_dict_from_row(existing_eval),
                    interview.current_difficulty,
                    next_question,
                )
            # Answer persisted but never evaluated (a prior attempt died
            # mid-turn) — only valid to resume if it's still the pending
            # question; falls through to the same current/in-progress
            # checks a net-new submission needs.

        if interview.status != SessionStatus.IN_PROGRESS:
            raise ConflictError("interview is not in progress", code="INTERVIEW_NOT_IN_PROGRESS")
        if interview.current_question_id != question_id:
            raise ConflictError(
                "question_id does not match this interview's current pending question",
                code="STALE_QUESTION_ID",
            )

        # --- Phase 1: durably persist the answer before any LLM call -----
        if answer is None:
            answer = Answer(
                question_id=question_id, answer_text=answer_text, submitted_at=datetime.now(UTC)
            )
            try:
                await self._answers.add(answer)
                await self._session.commit()
            except IntegrityError as exc:
                await self._session.rollback()
                logger.warning(
                    "interview.answer.race_detected",
                    interview_id=str(interview_id),
                    question_id=str(question_id),
                )
                raise ConflictError(
                    "an answer for this question was already submitted — retry to fetch its result",
                    code="ANSWER_ALREADY_SUBMITTED",
                ) from exc

        # --- Phase 2: re-acquire the lock, evaluate, adapt, persist -------
        interview = await self._interviews.get_owned_for_update(interview_id, user_id)
        if interview is None or interview.status != SessionStatus.IN_PROGRESS:
            raise ConflictError("interview is not in progress", code="INTERVIEW_NOT_IN_PROGRESS")
        if interview.current_question_id != question_id:
            # Something else (a concurrent duplicate request) already
            # advanced this turn in the window between phase 1 and here —
            # if it produced an evaluation, this is an idempotent replay;
            # otherwise it's a genuine conflict.
            existing_eval = await self._evaluations.get_by_answer_id(answer.id)
            if existing_eval is not None:
                next_question = (
                    await self._questions.get_with_round(interview.current_question_id)
                    if interview.current_question_id
                    else None
                )
                return (
                    interview,
                    _evaluation_dict_from_row(existing_eval),
                    interview.current_difficulty,
                    next_question,
                )
            raise ConflictError(
                "question_id does not match this interview's current pending question",
                code="STALE_QUESTION_ID",
            )

        round_ = await self._rounds.get_by_sequence(interview.id, interview.current_round_sequence)
        if round_ is None:
            raise UnprocessableEntityError("current round not found", code="ROUND_NOT_FOUND")

        context = build_execution_context(interview)
        round_questions = await self._questions.list_for_round(round_.id)
        round_question_ids = [q.id for q in round_questions]
        round_answers = await self._answers.list_for_questions(round_question_ids)
        answers_by_question_id = {a.question_id: a for a in round_answers}

        round_type_value = round_.round_type.value
        question_refs = [_question_to_ref(q, round_type_value) for q in round_questions]
        answer_refs = [
            _answer_to_ref(answers_by_question_id[q.id])
            for q in round_questions
            if q.id in answers_by_question_id
        ]
        question_refs_by_id = {q["id"]: q for q in question_refs}
        follow_up_count = _count_follow_ups_for_root(str(question.id), question_refs_by_id)

        all_evaluations = await self._evaluations.list_for_session(interview.id)
        personalization_state = _personalization_to_state(context.personalization)
        coding_candidates = await self._coding_candidates()
        coding_history = await self._questions.list_coding_problem_ids_for_session(interview.id)

        state: InterviewState = {
            "interview_id": str(interview.id),
            "user_id": str(user_id),
            "company": context.company_name,
            "role": context.role_title,
            "role_key": context.role_key,
            "mode": context.mode.value,
            "round_plan": [_round_plan_to_dict(r) for r in context.rounds],
            "current_round": round_.round_type.value,
            "current_round_index": round_.sequence_no,
            "current_question": _question_to_ref(question, round_type_value),
            "current_difficulty": interview.current_difficulty.value,
            "previous_difficulty": interview.current_difficulty.value,
            "last_question": _question_to_ref(question, round_type_value),
            "last_answer": _answer_to_ref(answer),
            "question_history": question_refs,
            "answer_history": answer_refs,
            "technical_evaluation": None,
            "communication_evaluation": None,
            "evaluation": None,
            "follow_up_count": follow_up_count,
            "round_score": None,
            "interview_scores": _compute_interview_scores(all_evaluations),
            "personalization_context": personalization_state,
            "resume_evidence_context": (
                personalization_state["evidence_snippets"] if personalization_state else []
            ),
            "trigger": "SUBMIT_ANSWER",
            "next_action": None,
            "interview_status": interview.status.value,
            "knowledge_context": "",
            "coding_problem_candidates": coding_candidates,
            "coding_problem_history": [str(i) for i in coding_history],
        }

        result = await self._invoke_graph(provider, interview.langgraph_thread_id, state)

        previous_difficulty = interview.current_difficulty
        evaluation_dict = result["evaluation"]
        eval_row = AnswerEvaluation(
            answer_id=answer.id,
            technical_score=evaluation_dict["technical"]["score"],
            technical_explanation=evaluation_dict["technical"]["explanation"],
            problem_solving_score=evaluation_dict["problem_solving"]["score"],
            problem_solving_explanation=evaluation_dict["problem_solving"]["explanation"],
            communication_score=evaluation_dict["communication"]["score"],
            communication_explanation=evaluation_dict["communication"]["explanation"],
            confidence_score=evaluation_dict["confidence"]["score"],
            confidence_explanation=evaluation_dict["confidence"]["explanation"],
            difficulty_signal=DifficultySignal(evaluation_dict["difficulty_signal"]),
        )
        await self._evaluations.add(eval_row)

        interview.current_difficulty = DifficultyLevel(result["current_difficulty"])

        next_question = await self._apply_round_transition_result(result, round_, interview)
        logger.info(
            "interview.answer.processed",
            interview_id=str(interview_id),
            question_id=str(question_id),
            answer_chars=len(answer_text),
            difficulty_signal=evaluation_dict["difficulty_signal"],
            status=interview.status.value,
        )
        return interview, evaluation_dict, previous_difficulty, next_question

    # --- Coding round completion (Module 6) -----------------------------

    async def complete_coding_round(
        self,
        *,
        interview_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        provider: InterviewAgentProvider,
    ) -> tuple[InterviewSession, Question | None]:
        """Called once a *final* code submission has been executed and
        graded by CodingRoundService (module §9 — Run/Submit never touch
        the graph themselves). Advances the interview exactly the way
        submit_answer's NEXT_ROUND path does, via the CODING_ROUND_COMPLETE
        trigger, which routes straight to round_transition — no
        evaluate_answer/adapt_difficulty for a round with no free-text
        answer or difficulty signal.

        Idempotency (module §22): keyed on the round's own status rather
        than an evaluation row (there is none here) — a round already
        RoundStatus.COMPLETED means a previous call already advanced the
        interview, so this replays the interview's CURRENT state rather
        than re-invoking the graph a second time.
        """
        interview = await self._interviews.get_owned_for_update(interview_id, user_id)
        if interview is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")

        question = await self._questions.get_with_round(question_id)
        if question is None:
            raise NotFoundError("question not found", code="QUESTION_NOT_FOUND")
        round_ = question.round

        if round_.status == RoundStatus.COMPLETED:
            logger.info(
                "interview.coding_round.idempotent_replay",
                interview_id=str(interview_id),
                question_id=str(question_id),
            )
            next_question = (
                await self._questions.get_with_round(interview.current_question_id)
                if interview.current_question_id
                else None
            )
            return interview, next_question

        if interview.status != SessionStatus.IN_PROGRESS:
            raise ConflictError("interview is not in progress", code="INTERVIEW_NOT_IN_PROGRESS")
        if interview.current_question_id != question_id:
            raise ConflictError(
                "question_id does not match this interview's current pending question",
                code="STALE_QUESTION_ID",
            )

        context = build_execution_context(interview)
        personalization_state = _personalization_to_state(context.personalization)
        coding_candidates = await self._coding_candidates()
        coding_history = await self._questions.list_coding_problem_ids_for_session(interview.id)
        all_evaluations = await self._evaluations.list_for_session(interview.id)

        state: InterviewState = {
            "interview_id": str(interview.id),
            "user_id": str(user_id),
            "company": context.company_name,
            "role": context.role_title,
            "role_key": context.role_key,
            "mode": context.mode.value,
            "round_plan": [_round_plan_to_dict(r) for r in context.rounds],
            "current_round": round_.round_type.value,
            "current_round_index": round_.sequence_no,
            "current_question": None,
            "current_difficulty": interview.current_difficulty.value,
            "previous_difficulty": interview.current_difficulty.value,
            "last_question": None,
            "last_answer": None,
            "question_history": [],
            "answer_history": [],
            "technical_evaluation": None,
            "communication_evaluation": None,
            "evaluation": None,
            "follow_up_count": 0,
            "round_score": None,
            "interview_scores": _compute_interview_scores(all_evaluations),
            "personalization_context": personalization_state,
            "resume_evidence_context": [],
            "trigger": "CODING_ROUND_COMPLETE",
            "next_action": None,
            "interview_status": interview.status.value,
            "knowledge_context": "",
            "coding_problem_candidates": coding_candidates,
            "coding_problem_history": [str(i) for i in coding_history],
        }

        result = await self._invoke_graph(provider, interview.langgraph_thread_id, state)
        next_question = await self._apply_round_transition_result(result, round_, interview)
        logger.info(
            "interview.coding_round.completed",
            interview_id=str(interview_id),
            question_id=str(question_id),
            status=interview.status.value,
        )
        return interview, next_question

    # --- Abandon -----------------------------------------------------------

    async def abandon(self, interview_id: uuid.UUID, user_id: uuid.UUID) -> InterviewSession:
        interview = await self._interviews.get_owned_for_update(interview_id, user_id)
        if interview is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")
        if interview.status not in (SessionStatus.NOT_STARTED, SessionStatus.IN_PROGRESS):
            raise ConflictError(
                "interview cannot be abandoned from its current status",
                code="INVALID_STATE_TRANSITION",
            )
        interview.status = SessionStatus.ABANDONED
        interview.completed_at = datetime.now(UTC)
        await self._session.commit()
        logger.info("interview.abandoned", interview_id=str(interview_id), user_id=str(user_id))
        return interview

    # --- Internals -----------------------------------------------------------

    async def _invoke_graph(
        self, provider: InterviewAgentProvider, thread_id: str, state: InterviewState
    ) -> dict:
        try:
            async with get_checkpointer() as checkpointer:
                graph = build_interview_graph(provider, checkpointer)
                return await graph.ainvoke(state, config={"configurable": {"thread_id": thread_id}})
        except InterviewIntelligenceTimeoutError as exc:
            raise ServiceUnavailableError(
                "the interview engine timed out generating a response — please retry",
                code="INTERVIEW_ENGINE_TIMEOUT",
            ) from exc
        except InterviewIntelligenceProviderError as exc:
            raise ServiceUnavailableError(
                "the interview engine is temporarily unavailable — please retry",
                code="INTERVIEW_ENGINE_UNAVAILABLE",
            ) from exc

    async def _apply_round_transition_result(
        self, result: dict, round_: InterviewRound, interview: InterviewSession
    ) -> Question | None:
        """The shared tail every trigger that can advance a round needs
        after invoking the graph (module §6: factored out rather than
        duplicated) — submit_answer's NEXT_ROUND path and
        complete_coding_round both call this. Marks the just-finished
        round COMPLETED, marks a new target round ACTIVE if the graph
        advanced to one, persists the next question (text or coding), and
        marks the interview COMPLETED if the graph decided there's nothing
        left. Commits once at the end.
        """
        now = datetime.now(UTC)
        round_changed = result["current_round_index"] != round_.sequence_no
        if round_changed or result["interview_status"] == "completed":
            await self._rounds.mark_status(round_, RoundStatus.COMPLETED, completed_at=now)

        next_question: Question | None = None
        if result["interview_status"] == "completed":
            interview.status = SessionStatus.COMPLETED
            interview.completed_at = now
            interview.current_question_id = None
            interview.current_round_sequence = result["current_round_index"]
        else:
            target_round = round_
            if round_changed:
                target_round = await self._rounds.get_by_sequence(
                    interview.id, result["current_round_index"]
                )
                if target_round is None:
                    raise UnprocessableEntityError("target round not found", code="ROUND_NOT_FOUND")
                await self._rounds.mark_status(target_round, RoundStatus.ACTIVE, started_at=now)
                interview.current_round_sequence = result["current_round_index"]

            next_question = await self._persist_question(result, target_round)
            interview.current_question_id = next_question.id

        await self._session.commit()
        await self._session.refresh(interview, attribute_names=["rounds"])
        return next_question

    async def _coding_candidates(self) -> list[CodingProblemCandidate]:
        """Every active catalog problem, shaped for graph state — see
        app/agents/state.py's CodingProblemCandidate docstring for why
        test case data is deliberately excluded.
        """
        problems = await self._coding_problems.list_active_for_selection()
        return [_coding_problem_to_candidate(p) for p in problems]

    async def _persist_question(self, result_state: dict, round_: InterviewRound) -> Question:
        ref: QuestionRef = result_state["current_question"]
        if ref["round_type"] == RoundType.CODING.value:
            return await self._persist_coding_question(ref, round_)

        question_type = (
            QuestionType.SYSTEM_DESIGN
            if ref["round_type"] == RoundType.SYSTEM_DESIGN.value
            else QuestionType.OPEN
        )
        question = Question(
            topic=ref["topic"],
            difficulty=DifficultyLevel(ref["difficulty"]),
            question_text=ref["text"],
            question_type=question_type,
            source=QuestionSource.GENERATED,
            asked_at=datetime.now(UTC),
            parent_question_id=(
                uuid.UUID(ref["parent_question_id"]) if ref["parent_question_id"] else None
            ),
        )
        # Assigned via the relationship (not round_id=round_.id) so
        # question.round is populated in-memory immediately — the router
        # reads question.round.round_type to shape the API response, and
        # this avoids ever depending on SQLAlchemy's lazy-load identity-map
        # optimization (correct here, but too implicit to rely on for
        # something that would otherwise risk a MissingGreenlet error in
        # an async session).
        question.round = round_
        await self._questions.add(question)
        return question

    async def _persist_coding_question(self, ref: QuestionRef, round_: InterviewRound) -> Question:
        """Module 6 — snapshots the selected catalog CodingProblem into a
        live Question (question_text carries the description, same as
        every other question_type) plus one QuestionTestCase per catalog
        test case (module §8's catalog-is-mutable/instance-is-immutable
        rule — see app/models/interview.py's Question docstring and
        app/models/coding.py's module docstring for the full reasoning).
        """
        if not ref["coding_problem_id"]:
            raise UnprocessableEntityError(
                "select_coding_problem_node returned a coding question ref with no "
                "coding_problem_id",
                code="CODING_PROBLEM_ID_MISSING",
            )
        problem_id = uuid.UUID(ref["coding_problem_id"])
        problem = await self._coding_problems.get_active_with_test_cases(problem_id)
        if problem is None:
            raise UnprocessableEntityError(
                "the selected catalog coding problem is no longer active", code="PROBLEM_NOT_FOUND"
            )

        question = Question(
            topic=ref["topic"],
            difficulty=DifficultyLevel(ref["difficulty"]),
            question_text=problem.description,
            question_type=QuestionType.CODING,
            source=QuestionSource.BANK,  # a catalog pick, not LLM-generated (module §8)
            asked_at=datetime.now(UTC),
            parent_question_id=None,  # coding questions never have follow-ups (module §8)
            coding_problem_id=problem.id,
            coding_snapshot={
                "title": problem.title,
                "constraints": problem.constraints,
                "expected_time_complexity": problem.expected_time_complexity,
                "expected_space_complexity": problem.expected_space_complexity,
                "supported_languages": problem.supported_languages,
                "starter_code": problem.starter_code,
                "topics": problem.topics,
            },
        )
        question.round = round_
        question.test_cases = [
            QuestionTestCase(
                input=tc.input,
                expected_output=tc.expected_output,
                is_sample=tc.is_sample,
                weight=tc.weight,
                sequence_no=tc.sequence_no,
            )
            for tc in problem.test_cases
        ]
        await self._questions.add(question)
        return question


# --- Pure helpers (state <-> ORM/context conversion) ------------------------


def _first_executable_round_index(rounds: list[RoundExecutionPlan]) -> int | None:
    """The lowest sequence_no in the plan — Module 6 removed the only
    reason this ever skipped anything (coding rounds are real now, see
    app/agents/nodes/coding_problem_selector.py), so this returns None
    only for a genuinely empty plan (a planning bug Module 4's planner
    should never actually produce, but guarded rather than assumed).
    """
    if not rounds:
        return None
    return min(round_plan.sequence_no for round_plan in rounds)


def _round_plan_to_dict(r: RoundExecutionPlan) -> dict:
    return {
        "round_type": r.round_type.value,
        "sequence_no": r.sequence_no,
        "weight": r.weight,
        "planned_difficulty": r.planned_difficulty.value,
        "is_required": r.is_required,
    }


def _personalization_to_state(
    personalization: PersonalizationContext | None,
) -> PersonalizationContextState | None:
    if personalization is None:
        return None
    return {
        "skills": personalization.skills,
        "focus_areas": personalization.focus_areas,
        "project_titles": personalization.project_titles,
        "evidence_snippets": personalization.evidence_snippets,
    }


def _question_to_ref(question: Question, round_type: str) -> QuestionRef:
    # Takes round_type explicitly rather than reading question.round —
    # that relationship is lazy and would need an extra eager-load or a
    # blocking lazy-load (unsafe in an async session) for something every
    # caller already knows from the InterviewRound row it fetched.
    return {
        "id": str(question.id),
        "text": question.question_text,
        "topic": question.topic,
        "round_type": round_type,
        "difficulty": question.difficulty.value,
        "parent_question_id": (
            str(question.parent_question_id) if question.parent_question_id else None
        ),
        "coding_problem_id": (
            str(question.coding_problem_id) if question.coding_problem_id else None
        ),
    }


def _coding_problem_to_candidate(problem: CodingProblem) -> CodingProblemCandidate:
    return {
        "id": str(problem.id),
        "slug": problem.slug,
        "title": problem.title,
        "description": problem.description,
        "difficulty": problem.difficulty.value,
        "topics": problem.topics,
        "constraints": problem.constraints,
        "expected_time_complexity": problem.expected_time_complexity,
        "expected_space_complexity": problem.expected_space_complexity,
        "supported_languages": problem.supported_languages,
        "starter_code": problem.starter_code,
        "role_keys": problem.role_keys,
    }


def _answer_to_ref(answer: Answer) -> AnswerRef:
    return {
        "id": str(answer.id),
        "question_id": str(answer.question_id),
        "text": answer.answer_text or "",
    }


def _empty_scores() -> InterviewScores:
    return {
        "technical": 0.0,
        "problem_solving": 0.0,
        "communication": 0.0,
        "confidence": 0.0,
        "answered_count": 0,
    }


def _compute_interview_scores(evaluations: list[AnswerEvaluation]) -> InterviewScores:
    if not evaluations:
        return _empty_scores()
    count = len(evaluations)
    return {
        "technical": sum(float(e.technical_score) for e in evaluations) / count,
        "problem_solving": sum(float(e.problem_solving_score) for e in evaluations) / count,
        "communication": sum(float(e.communication_score) for e in evaluations) / count,
        "confidence": sum(float(e.confidence_score) for e in evaluations) / count,
        "answered_count": count,
    }


def _count_follow_ups_for_root(question_id: str, questions_by_id: dict[str, QuestionRef]) -> int:
    """How many questions in the current round descend from the same root
    as `question_id` (module §8's follow-up cap needs this — see
    app/agents/state.py's QuestionRef docstring for why chains, not a
    counter column, represent this).
    """

    def _root_of(qid: str) -> str:
        seen = {qid}
        current = questions_by_id.get(qid)
        while current is not None and current["parent_question_id"] is not None:
            parent_id = current["parent_question_id"]
            if parent_id in seen:  # defensive: never trust external data to be acyclic
                break
            seen.add(parent_id)
            current = questions_by_id.get(parent_id)
            if current is None:
                return parent_id
        return current["id"] if current is not None else qid

    root = _root_of(question_id)
    return sum(1 for qid in questions_by_id if qid != root and _root_of(qid) == root)


def _evaluation_dict_from_row(row: AnswerEvaluation) -> dict:
    return {
        "technical": {
            "score": float(row.technical_score),
            "explanation": row.technical_explanation,
        },
        "problem_solving": {
            "score": float(row.problem_solving_score),
            "explanation": row.problem_solving_explanation,
        },
        "communication": {
            "score": float(row.communication_score),
            "explanation": row.communication_explanation,
        },
        "confidence": {
            "score": float(row.confidence_score),
            "explanation": row.confidence_explanation,
        },
        "difficulty_signal": row.difficulty_signal.value,
    }
