"""InterviewPlannerService — the Module 4 use case: turn a candidate's
(company, role, template, mode, difficulty, resume) selection into a
validated, immutable InterviewSession + InterviewRound plan (module §1,
§9). Deterministic end to end — no LLM call anywhere in this file
(module §18); AUTO difficulty resolves from Module 3's already-computed
`resume_gap_analysis`, never a fresh model call.

Mirrors ResumeService/AuthService's shape: routers call exactly these
methods, own no SQL/transaction logic themselves. One commit per
`create_plan` call — the session row and every one of its rounds are
persisted atomically (module §14/§20), or none of them are.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, UnprocessableEntityError
from app.core.logging import get_logger
from app.models.enums import (
    DifficultyLevel,
    InterviewMode,
    ParsedStatus,
    RequestedDifficulty,
    RoundStatus,
    RoundType,
    SessionStatus,
)
from app.models.interview import InterviewRound, InterviewSession
from app.models.planning import Company, InterviewTemplate, Role
from app.models.resume import Resume
from app.models.user import User
from app.repositories.interview import InterviewSessionRepository
from app.repositories.planning import CompanyRepository, InterviewTemplateRepository, RoleRepository
from app.repositories.resume import ResumeRepository
from app.schemas.interview import InterviewPlanRequest
from app.services.resume.interview_context import build_resume_interview_context

logger = get_logger(__name__)

# Modes that make no sense without a resume to ground them in — checked
# in addition to "does the chosen template have a resume_discussion round",
# since a candidate could in principle attach a resume_discussion round to
# a template tagged with a different mode.
_MODES_REQUIRING_RESUME = {InterviewMode.RESUME_DEEP_DIVE}

_SAFE_DEFAULT_DIFFICULTY = DifficultyLevel.MEDIUM


class InterviewPlannerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._companies = CompanyRepository(session)
        self._roles = RoleRepository(session)
        self._templates = InterviewTemplateRepository(session)
        self._resumes = ResumeRepository(session)
        self._interviews = InterviewSessionRepository(session)

    # --- Reads -----------------------------------------------------------

    async def get_owned(self, session_id: uuid.UUID, user_id: uuid.UUID) -> InterviewSession:
        session = await self._interviews.get_owned(session_id, user_id)
        if session is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")
        return session

    async def list_for_user(
        self, user_id: uuid.UUID, *, status: str | None = None
    ) -> list[InterviewSession]:
        return await self._interviews.list_owned(user_id, status=status)

    # --- Planning ----------------------------------------------------------

    async def create_plan(self, *, user: User, request: InterviewPlanRequest) -> InterviewSession:
        company = await self._resolve_company(request.company_id)
        role = await self._resolve_role(request.role_id)
        template = await self._resolve_template(request.template_id)
        self._validate_template_matches(template, company=company, role=role)

        resolved_mode = self._resolve_mode(template, request.mode)
        resume = await self._resolve_resume(
            user_id=user.id, resume_id=request.resume_id, template=template, mode=resolved_mode
        )
        starting_difficulty, difficulty_reasons = self._resolve_difficulty(
            requested=request.difficulty, role=role, resume=resume
        )

        plan_snapshot = self._build_plan_snapshot(
            company=company,
            role=role,
            template=template,
            mode=resolved_mode,
            requested_difficulty=request.difficulty,
            starting_difficulty=starting_difficulty,
            difficulty_reasons=difficulty_reasons,
            resume=resume,
        )

        interview = InterviewSession(
            user_id=user.id,
            resume_id=resume.id if resume is not None else None,
            company_id=company.id if company is not None else None,
            role_id=role.id,
            template_id=template.id,
            status=SessionStatus.NOT_STARTED,
            current_round_sequence=0,
            current_difficulty=starting_difficulty,
            requested_difficulty=request.difficulty,
            starting_difficulty=starting_difficulty,
            mode=resolved_mode,
            plan_snapshot=plan_snapshot,
            # Module 5 assigns the real LangGraph checkpoint thread when the
            # interview actually starts; this placeholder only satisfies the
            # NOT NULL/unique constraint for a session that has been planned
            # but not yet started (Database.md's langgraph_thread_id is
            # documented as linking to a checkpoint, which doesn't exist yet
            # for a PLANNED/not_started session).
            langgraph_thread_id=f"planned:{uuid.uuid4().hex}",
        )
        for template_round in sorted(template.rounds, key=lambda r: r.sequence_no):
            interview.rounds.append(
                InterviewRound(
                    template_round_id=template_round.id,
                    round_type=template_round.round_type,
                    sequence_no=template_round.sequence_no,
                    weight=template_round.weight,
                    planned_difficulty=template_round.difficulty_override or starting_difficulty,
                    status=RoundStatus.PENDING,
                )
            )

        self._session.add(interview)
        await self._session.commit()
        await self._session.refresh(interview, attribute_names=["rounds"])
        logger.info(
            "interview.planned",
            interview_id=str(interview.id),
            user_id=str(user.id),
            mode=resolved_mode.value,
            starting_difficulty=starting_difficulty.value,
            resume_id=str(resume.id) if resume else None,
        )
        return interview

    # --- Validation helpers ------------------------------------------------

    async def _resolve_company(self, company_id: uuid.UUID | None) -> Company | None:
        if company_id is None:
            return None
        company = await self._companies.get_active(company_id)
        if company is None:
            raise NotFoundError("company not found or inactive", code="COMPANY_NOT_FOUND")
        return company

    async def _resolve_role(self, role_id: uuid.UUID) -> Role:
        role = await self._roles.get_active(role_id)
        if role is None:
            raise NotFoundError("role not found or inactive", code="ROLE_NOT_FOUND")
        return role

    async def _resolve_template(self, template_id: uuid.UUID) -> InterviewTemplate:
        template = await self._templates.get_active_with_rounds(template_id)
        if template is None:
            raise NotFoundError(
                "interview template not found or inactive", code="TEMPLATE_NOT_FOUND"
            )
        if not template.rounds:
            # Defensive — should never happen for seeded/authored templates,
            # but a template with zero rounds can't produce a usable plan.
            raise UnprocessableEntityError(
                "interview template has no configured rounds", code="TEMPLATE_EMPTY"
            )
        return template

    @staticmethod
    def _validate_template_matches(
        template: InterviewTemplate, *, company: Company | None, role: Role
    ) -> None:
        if template.role_id != role.id:
            raise UnprocessableEntityError(
                "template does not belong to the selected role", code="TEMPLATE_ROLE_MISMATCH"
            )
        template_company_id = template.company_id
        request_company_id = company.id if company is not None else None
        if template_company_id != request_company_id:
            raise UnprocessableEntityError(
                "template does not belong to the selected company",
                code="TEMPLATE_COMPANY_MISMATCH",
            )

    @staticmethod
    def _resolve_mode(
        template: InterviewTemplate, requested_mode: InterviewMode | None
    ) -> InterviewMode:
        if requested_mode is None:
            return template.mode
        if requested_mode != template.mode:
            raise UnprocessableEntityError(
                f"requested mode {requested_mode.value!r} is incompatible with template "
                f"mode {template.mode.value!r}",
                code="INCOMPATIBLE_MODE",
            )
        return requested_mode

    async def _resolve_resume(
        self,
        *,
        user_id: uuid.UUID,
        resume_id: uuid.UUID | None,
        template: InterviewTemplate,
        mode: InterviewMode,
    ) -> Resume | None:
        resume_required = mode in _MODES_REQUIRING_RESUME or any(
            r.round_type == RoundType.RESUME_DISCUSSION for r in template.rounds
        )

        if resume_id is not None:
            # Explicit selection: ownership and readiness are both hard
            # requirements — never silently fall back (module §8/§16).
            resume = await self._resumes.get_owned_with_children(resume_id, user_id)
            if resume is None:
                raise NotFoundError("resume not found", code="RESUME_NOT_FOUND")
            if resume.parsed_status != ParsedStatus.DONE:
                raise ConflictError(
                    "selected resume has not finished analysis yet",
                    details={"parsed_status": resume.parsed_status.value},
                    code="RESUME_NOT_READY",
                )
            return resume

        # No explicit selection: fall back to the active resume, but only
        # if it's actually usable — an active-but-still-processing resume
        # is simply treated as "no resume available" here, not an error,
        # unless the mode/template strictly requires one.
        active = await self._resumes.get_active_for_user_with_children(user_id)
        if active is not None and active.parsed_status == ParsedStatus.DONE:
            return active

        if resume_required:
            raise UnprocessableEntityError(
                "this interview mode/template requires an analyzed resume — "
                "upload/select one, or choose a mode that does not require one",
                code="RESUME_REQUIRED",
            )
        return None

    @staticmethod
    def _resolve_difficulty(
        *, requested: RequestedDifficulty, role: Role, resume: Resume | None
    ) -> tuple[DifficultyLevel, list[str]]:
        if requested != RequestedDifficulty.AUTO:
            level = DifficultyLevel(requested.value)
            return level, [f"Candidate explicitly requested {level.value} difficulty."]

        gap = resume.gap_analysis if resume is not None else None
        if gap is None:
            return _SAFE_DEFAULT_DIFFICULTY, [
                "AUTO requested but no resume gap-analysis was available — "
                f"defaulted to the documented safe default ({_SAFE_DEFAULT_DIFFICULTY.value})."
            ]

        reasons = list(gap.difficulty_reasons)
        if role.role_key and gap.role_key == role.role_key:
            reasons.insert(
                0,
                f"AUTO difficulty resolved from the resume's gap-analysis for "
                f"role_key={gap.role_key!r} (matches the selected role): "
                f"{gap.recommended_difficulty.value}.",
            )
        else:
            reasons.insert(
                0,
                f"AUTO difficulty resolved from the resume's most recent gap-analysis "
                f"(role_key={gap.role_key!r}), which does not exactly match the selected "
                f"role (role_key={role.role_key!r}) — used as the best available signal: "
                f"{gap.recommended_difficulty.value}.",
            )
        return gap.recommended_difficulty, reasons

    @staticmethod
    def _build_plan_snapshot(
        *,
        company: Company | None,
        role: Role,
        template: InterviewTemplate,
        mode: InterviewMode,
        requested_difficulty: RequestedDifficulty,
        starting_difficulty: DifficultyLevel,
        difficulty_reasons: list[str],
        resume: Resume | None,
    ) -> dict:
        rounds_snapshot = [
            {
                "round_type": r.round_type.value,
                "sequence_no": r.sequence_no,
                "weight": _to_float(r.weight),
                "planned_difficulty": (r.difficulty_override or starting_difficulty).value,
                "is_required": r.is_required,
            }
            for r in sorted(template.rounds, key=lambda r: r.sequence_no)
        ]

        personalization = None
        if resume is not None:
            ctx = build_resume_interview_context(resume)
            gap = resume.gap_analysis
            personalization = {
                "resume_id": str(ctx.resume_id),
                "skills": ctx.skills,
                "focus_areas": gap.focus_areas if gap else [],
                "missing_skills": gap.missing_skills if gap else [],
                "matching_skills": gap.matching_skills if gap else [],
                "project_titles": [p.title for p in ctx.projects],
                # Capped — a plan snapshot is meant to be a compact,
                # fast-to-read record (module §20), not a copy of the
                # entire resume; the full data still lives on the resume
                # row itself via resume_id.
                "evidence_snippets": ctx.evidence_snippets[:20],
            }

        return {
            "company": (
                {"id": str(company.id), "slug": company.slug, "name": company.name}
                if company is not None
                else None
            ),
            "role": {
                "id": str(role.id),
                "role_key": role.role_key,
                "title": role.title,
                "level": role.level.value,
            },
            "template": {
                "id": str(template.id),
                "name": template.name,
                "description": template.description,
            },
            "mode": mode.value,
            "rounds": rounds_snapshot,
            "difficulty": {
                "requested": requested_difficulty.value,
                "starting": starting_difficulty.value,
                "reasons": difficulty_reasons,
            },
            "personalization": personalization,
        }


def _to_float(value: Decimal | float) -> float:
    return float(value)
