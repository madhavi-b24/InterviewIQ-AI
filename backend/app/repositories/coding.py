"""Coding-round repositories (Module 6). `CodingProblemRepository` mirrors
the catalog repositories in app/repositories/planning.py (is_active
filtered in-query, no ownership filter — shared reference data).
`CodeSubmissionRepository`/`CodeSubmissionTestResultRepository` mirror
app/repositories/interview.py's execution-domain repos (no ownership
filter of their own — the caller has already verified ownership of the
parent InterviewSession/Answer before reaching these).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.coding import CodingProblem
from app.models.evaluation import CodingEvaluation
from app.models.interview import CodeSubmission, CodeSubmissionTestResult
from app.repositories.base import BaseRepository

# selectinload chain reused by both read methods below — the API layer
# needs `answer.question_id` and `test_results[i].test_case.{input,
# expected_output}` to shape CodeSubmissionOut without any relationship
# access risking an implicit lazy load (MissingGreenlet under asyncpg).
_SUBMISSION_LOAD_OPTIONS = (
    selectinload(CodeSubmission.answer),
    selectinload(CodeSubmission.test_results).selectinload(CodeSubmissionTestResult.test_case),
)


class CodingProblemRepository(BaseRepository[CodingProblem]):
    model = CodingProblem

    async def list_active_for_selection(self) -> list[CodingProblem]:
        """Every active catalog problem, ordered by slug (a small, stable
        set — module §8's "small, high-quality catalog", not hundreds of
        rows) — no difficulty/role filter here. Difficulty and language
        aren't known yet at the point a round is about to start: language
        is chosen by the candidate at Run/Submit time (module §6), and
        difficulty may still change mid-turn (adapt_difficulty runs before
        round_transition on the SUBMIT_ANSWER path). Filtering therefore
        happens deterministically inside the graph, against whatever
        current_difficulty/role_key turn out to be by the time
        select_coding_problem_node actually runs — see
        app/agents/policy.py's select_coding_problem. This method never
        eager-loads test_cases — selection never needs them (hidden test
        data has no reason to leave the repository/service layer this
        early — module §8).
        """
        stmt = (
            select(CodingProblem)
            .where(CodingProblem.is_active.is_(True))
            .order_by(CodingProblem.slug)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_with_test_cases(self, problem_id: uuid.UUID) -> CodingProblem | None:
        stmt = (
            select(CodingProblem)
            .where(CodingProblem.id == problem_id, CodingProblem.is_active.is_(True))
            .options(selectinload(CodingProblem.test_cases))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class CodeSubmissionRepository(BaseRepository[CodeSubmission]):
    model = CodeSubmission

    async def get_with_test_results(self, submission_id: uuid.UUID) -> CodeSubmission | None:
        stmt = (
            select(CodeSubmission)
            .where(CodeSubmission.id == submission_id)
            .options(*_SUBMISSION_LOAD_OPTIONS)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_answer(self, answer_id: uuid.UUID) -> list[CodeSubmission]:
        stmt = (
            select(CodeSubmission)
            .where(CodeSubmission.answer_id == answer_id)
            .options(*_SUBMISSION_LOAD_OPTIONS)
            .order_by(CodeSubmission.attempt_no.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_final_for_answer(self, answer_id: uuid.UUID) -> CodeSubmission | None:
        stmt = select(CodeSubmission).where(
            CodeSubmission.answer_id == answer_id, CodeSubmission.is_final.is_(True)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def next_attempt_no(self, answer_id: uuid.UUID) -> int:
        submissions = await self.list_for_answer(answer_id)
        if not submissions:
            return 1
        return max(s.attempt_no for s in submissions) + 1


class CodeSubmissionTestResultRepository(BaseRepository[CodeSubmissionTestResult]):
    model = CodeSubmissionTestResult


class CodingEvaluationRepository(BaseRepository[CodingEvaluation]):
    model = CodingEvaluation

    async def get_by_submission_id(self, code_submission_id: uuid.UUID) -> CodingEvaluation | None:
        stmt = select(CodingEvaluation).where(
            CodingEvaluation.code_submission_id == code_submission_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
