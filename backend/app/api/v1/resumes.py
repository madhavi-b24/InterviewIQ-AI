"""Resume Intelligence API — API.md §2, extended per module §16.

`POST /resumes/{resume_id}/gap-analysis` deviates from API.md's literal
`{ "target_role_id": uuid }` body — see GapAnalysisRequest's docstring
for why (Module 4's `roles` table isn't seeded yet). Every path and every
other method matches API.md exactly. Thin per Architecture.md §4: parses
the request, calls exactly one ResumeService method, shapes the response
— no SQL, storage, or LLM calls here.
"""

import uuid

from fastapi import APIRouter, File, Response, UploadFile, status

import app.jobs.resume_processing  # noqa: F401 — import registers JOB_HANDLERS["process_resume"]
from app.api.deps import CurrentUser, JobRunnerDep, ResumeServiceDep
from app.core.config import get_settings
from app.core.exceptions import UnprocessableEntityError
from app.schemas.resume import (
    AchievementOut,
    CertificationOut,
    EducationOut,
    ExperienceOut,
    GapAnalysisRequest,
    ProjectOut,
    ResumeAnalysisResponse,
    ResumeDetail,
    ResumeSummary,
    RoleReadinessResponse,
    SkillOut,
)
from app.services.resume.role_profiles import get_role_profile

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    current_user: CurrentUser,
    resume_service: ResumeServiceDep,
    job_runner: JobRunnerDep,
    file: UploadFile = File(...),
) -> ResumeSummary:
    settings = get_settings()
    max_bytes = settings.RESUME_MAX_UPLOAD_MB * 1024 * 1024
    # Bounded read: never buffers more than max_bytes + 1 regardless of
    # what the client claims/sends — pdf.py's size check then rejects
    # anything that actually hit the +1 with a clear FILE_TOO_LARGE error.
    content = await file.read(max_bytes + 1)
    if not content:
        raise UnprocessableEntityError("Uploaded file is empty.", code="EMPTY_FILE")

    resume = await resume_service.upload(
        user=current_user,
        filename=file.filename,
        content_type=file.content_type,
        content=content,
    )
    job_runner.enqueue("process_resume", {"resume_id": str(resume.id)})
    return ResumeSummary.model_validate(resume)


@router.get("")
async def list_resumes(
    current_user: CurrentUser, resume_service: ResumeServiceDep
) -> list[ResumeSummary]:
    resumes = await resume_service.list_resumes(current_user.id)
    return [ResumeSummary.model_validate(resume) for resume in resumes]


@router.get("/{resume_id}")
async def get_resume(
    resume_id: uuid.UUID, current_user: CurrentUser, resume_service: ResumeServiceDep
) -> ResumeDetail:
    resume = await resume_service.get_resume(resume_id, current_user.id)
    return ResumeDetail.model_validate(resume)


@router.get("/{resume_id}/analysis")
async def get_resume_analysis(
    resume_id: uuid.UUID, current_user: CurrentUser, resume_service: ResumeServiceDep
) -> ResumeAnalysisResponse:
    resume = await resume_service.get_resume_with_analysis(resume_id, current_user.id)
    return ResumeAnalysisResponse(
        resume_id=resume.id,
        parsed_status=resume.parsed_status,
        processing_error=resume.processing_error,
        candidate_name=resume.candidate_name,
        professional_summary=resume.professional_summary,
        detected_sections=sorted(resume.detected_sections.keys()),
        education=[EducationOut.model_validate(item) for item in resume.education],
        skills=[SkillOut.model_validate(item) for item in resume.skills],
        projects=[ProjectOut.model_validate(item) for item in resume.projects],
        experience=[ExperienceOut.model_validate(item) for item in resume.experience],
        certifications=[CertificationOut.model_validate(item) for item in resume.certifications],
        achievements=[AchievementOut.model_validate(item) for item in resume.achievements],
    )


@router.post("/{resume_id}/gap-analysis")
async def generate_gap_analysis(
    resume_id: uuid.UUID,
    data: GapAnalysisRequest,
    current_user: CurrentUser,
    resume_service: ResumeServiceDep,
) -> RoleReadinessResponse:
    gap = await resume_service.generate_role_readiness(
        resume_id=resume_id, user_id=current_user.id, role_key=data.role_key
    )
    role_profile = get_role_profile(gap.role_key)
    return RoleReadinessResponse(
        resume_id=resume_id,
        role_key=gap.role_key,
        role_label=role_profile.label if role_profile else gap.role_key,
        matching_skills=gap.matching_skills,
        missing_skills=gap.missing_skills,
        strengths=gap.strengths,
        focus_areas=gap.focus_areas,
        recommended_difficulty=gap.recommended_difficulty,
        recommended_level_label=RoleReadinessResponse.level_label(gap.recommended_difficulty),
        confidence=gap.confidence,
        reasons=gap.difficulty_reasons,
        explanation=gap.explanation,
        generated_at=gap.generated_at,
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: uuid.UUID, current_user: CurrentUser, resume_service: ResumeServiceDep
) -> Response:
    await resume_service.delete_resume(resume_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
