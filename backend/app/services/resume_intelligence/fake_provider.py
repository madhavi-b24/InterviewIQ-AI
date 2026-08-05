"""FakeResumeIntelligenceProvider — deterministic, rule-based, no network
call. Wired only via `app.dependency_overrides` in tests/conftest.py,
never selectable through Settings (see RESUME_INTELLIGENCE_PROVIDER's
docstring) — a misconfigured deployment can never end up fabricating
resume data through this path.

Deliberately simple regex/split-based parsing rather than trying to
mimic Gemini's judgment — its job is to prove ResumeService's
persistence/error-handling logic against a schema-valid response, and to
let tests deterministically request a timeout/failure without touching
real infrastructure.
"""

import re

from app.services.resume_intelligence.provider import (
    ResumeIntelligenceProviderError,
    ResumeIntelligenceTimeoutError,
)
from app.services.resume_intelligence.schemas import (
    ExtractedExperience,
    ExtractedProfile,
    ExtractedProject,
    ExtractedSkill,
)


class FakeResumeIntelligenceProvider:
    def __init__(
        self, *, fail: bool = False, timeout: bool = False, malformed: bool = False
    ) -> None:
        self.fail = fail
        self.timeout = timeout
        self.malformed = malformed
        self.calls: list[str] = []

    def reset(self) -> None:
        self.fail = False
        self.timeout = False
        self.malformed = False
        self.calls = []

    async def extract(self, *, resume_text: str, sections: dict[str, str]) -> ExtractedProfile:
        self.calls.append(resume_text)
        if self.timeout:
            raise ResumeIntelligenceTimeoutError("fake provider: simulated timeout")
        if self.fail:
            raise ResumeIntelligenceProviderError("fake provider: simulated provider failure")
        if self.malformed:
            # Exercises ResumeService's defensive-parsing path: a provider
            # that raises this exact error is indistinguishable from one
            # whose JSON failed pydantic validation upstream.
            raise ResumeIntelligenceProviderError(
                "fake provider: simulated malformed/unparseable response"
            )

        lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
        candidate_name = lines[0] if lines else None

        skills: list[ExtractedSkill] = []
        skills_text = sections.get("skills", "")
        for token in re.split(r"[,\n]", skills_text):
            token = token.strip()
            if token:
                skills.append(ExtractedSkill(name=token, source="explicit", evidence=skills_text))

        projects: list[ExtractedProject] = []
        projects_text = sections.get("projects", "")
        if projects_text:
            project_lines = [ln for ln in projects_text.splitlines() if ln.strip()]
            projects.append(
                ExtractedProject(
                    title=project_lines[0] if project_lines else "Untitled Project",
                    description=projects_text,
                    evidence=projects_text,
                )
            )

        experience: list[ExtractedExperience] = []
        experience_text = sections.get("experience", "")
        if experience_text:
            experience_lines = [ln for ln in experience_text.splitlines() if ln.strip()]
            first_line = experience_lines[0] if experience_lines else "Unknown Role"
            company, _, title = first_line.partition(",")
            experience.append(
                ExtractedExperience(
                    company=(company.strip() or "Unknown") if "," in first_line else "Unknown",
                    title=(title.strip() or first_line) if "," in first_line else first_line,
                    description=experience_text,
                    evidence=experience_text,
                )
            )

        return ExtractedProfile(
            candidate_name=candidate_name,
            professional_summary=sections.get("summary") or None,
            skills=skills,
            projects=projects,
            experience=experience,
        )


# Module-level singleton: app/jobs/resume_processing.py builds its provider
# via app/services/resume/factories.py, which has no request context to
# hang an app.dependency_overrides-style swap off of. Tests mutate this
# singleton's .fail/.timeout/.malformed directly (see
# tests/conftest.py's autouse reset fixture) instead of constructing a new
# instance per test.
_singleton = FakeResumeIntelligenceProvider()


def get_fake_resume_intelligence_provider() -> FakeResumeIntelligenceProvider:
    return _singleton
