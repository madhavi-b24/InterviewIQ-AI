"""The structured-output contract ReportGenerationProvider implementations
must return (Database.md §7).

**Gemini structured-output constraint** — the same rule
app/services/code_evaluation/schemas.py (and resume_intelligence's/
interview_intelligence's own schemas) were written under from the start:
no field below may have a non-None default. `X | None = None` and
`Field(default_factory=list)` are safe; `Field(default=<anything but
None>)` is not.

Deliberately excludes every numeric score — section scores, overall
score, and weak-area severity are all computed deterministically in
app/agents/policy.py before this provider is ever called (module §11's
rule, extended to report generation), never asked of the model. No
chain-of-thought (module §20): every field here is an explanation, a
short evidence-citing narrative, or a structured list — nothing asks for
the model's internal reasoning.

Independent of app/models (mirrors every other provider package's own
independence) — `resource_type` is a plain `Literal` of the same string
values as `app.models.enums.ResourceType`, not an import of that enum;
ReportService converts the string when building the ORM row.
"""

from typing import Literal

from pydantic import BaseModel, Field


class WeakAreaContent(BaseModel):
    topic: str = Field(description="A specific topic, e.g. 'Dynamic Programming', 'SQL joins'")
    section: Literal["technical", "coding", "communication", "problem_solving", "confidence"] = (
        Field(description="Which of the five report sections this weak area belongs to")
    )
    evidence_text: str = Field(
        description="Quoted/paraphrased from the actual evidence that triggered this — never a "
        "generic statement"
    )


class StrongAreaContent(BaseModel):
    topic: str
    evidence_text: str


class RoadmapItemContent(BaseModel):
    topic: str = Field(description="Should correspond to one of the report's weak areas")
    resource_title: str
    resource_url: str | None = None
    resource_type: Literal["article", "video", "course", "practice"]
    priority: int = Field(description="1 = highest priority; lower numbers come first")


class ReportContentResult(BaseModel):
    technical_explanation: str
    problem_solving_explanation: str
    communication_explanation: str
    confidence_explanation: str
    # Only a session with a coding round has a coding section score to
    # explain — None when there isn't one, never a fabricated placeholder.
    coding_explanation: str | None = None
    overall_explanation: str
    summary_text: str = Field(
        description="A short overall narrative summary of the candidate's performance"
    )
    weak_areas: list[WeakAreaContent] = Field(default_factory=list)
    strong_areas: list[StrongAreaContent] = Field(default_factory=list)
    roadmap_items: list[RoadmapItemContent] = Field(default_factory=list)
