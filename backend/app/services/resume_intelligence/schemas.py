"""The structured-extraction contract every ResumeIntelligenceProvider
implementation must return (module §5, §6, §8).

This is deliberately the *only* place that defines "what a structured
resume looks like" for the LLM stage — GeminiResumeIntelligenceProvider
passes `ExtractedProfile` as Gemini's `response_schema` (structured
output), and FakeResumeIntelligenceProvider constructs the same model by
hand. ResumeService never sees raw LLM JSON, only this validated shape.

Every fact-bearing item (skill/project/experience/education/certification)
carries an `evidence` field — module §6's provenance requirement. It's
Optional because the model may occasionally omit it for an implicit/
inferred fact, not because evidence is optional in the product sense;
ResumeService still persists whatever evidence text is present.
"""

from pydantic import BaseModel, Field


class ExtractedEducation(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = Field(
        default=None, description="Best-effort, e.g. '2019' or '2019-08'"
    )
    end_date: str | None = None
    evidence: str | None = Field(
        default=None, description="Verbatim or near-verbatim resume text this was extracted from"
    )


class ExtractedSkill(BaseModel):
    name: str = Field(description="Skill exactly as it appears/is implied on the resume")
    source: str = Field(
        default="explicit",
        description=(
            "'explicit' if listed in a skills section, "
            "'inferred' if only implied by project/experience text"
        ),
    )
    evidence: str | None = None


class ExtractedProject(BaseModel):
    title: str
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(
        default_factory=list,
        description="Measurable outcomes only if explicitly stated — never invented",
    )
    start_date: str | None = None
    end_date: str | None = None
    evidence: str | None = None


class ExtractedExperience(BaseModel):
    company: str
    title: str
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    evidence: str | None = None


class ExtractedCertification(BaseModel):
    name: str
    issuer: str | None = None
    issued_date: str | None = None
    evidence: str | None = None


class ExtractedAchievement(BaseModel):
    description: str
    evidence: str | None = None


class ExtractedProfile(BaseModel):
    """Top-level structured-extraction result. Every list defaults to
    empty — a resume genuinely missing a section (module §5: "do not
    assume every resume contains every section") produces an empty list,
    never a fabricated entry.
    """

    candidate_name: str | None = None
    professional_summary: str | None = None
    education: list[ExtractedEducation] = Field(default_factory=list)
    skills: list[ExtractedSkill] = Field(default_factory=list)
    projects: list[ExtractedProject] = Field(default_factory=list)
    experience: list[ExtractedExperience] = Field(default_factory=list)
    certifications: list[ExtractedCertification] = Field(default_factory=list)
    achievements: list[ExtractedAchievement] = Field(default_factory=list)
