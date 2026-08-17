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

**Gemini structured-output constraint — do not give any field a non-None
default.** `google-genai`'s client-side schema converter
(`_transformers.process_schema`) raises `ValueError("Default value is not
supported in the response schema for the Gemini API.")` for any field whose
generated JSON Schema includes a `"default"` key with a non-null value.
Pydantic v2 only emits that key when a field has an explicit, non-None
`default=...` (e.g. `Field(default="explicit")` — the bug this comment
guards against); a plain `X | None = None` field serializes as
`"default": null`, which the SDK explicitly allows, and a
`default_factory=list` field isn't materialized into the schema's
`"default"` at all (Pydantic just omits it from `required`). So: `X | None
= None` and `list[X] = Field(default_factory=list)` are both safe here;
`= Field(default=<anything but None>)` is not. If you need a
Gemini-required-with-fallback field, enforce the fallback in
`GeminiResumeIntelligenceProvider._parse_response` after validation, not as
a Pydantic default on the schema Gemini itself receives.
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
    # No default here (deliberately) — see the module docstring's Gemini
    # compatibility note. The system prompt (gemini_provider.py, rule 5)
    # already instructs the model to always classify every skill, so
    # requiring the field costs nothing behaviorally; it only removes a
    # Python-level fallback the model was never actually expected to need.
    source: str = Field(
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
