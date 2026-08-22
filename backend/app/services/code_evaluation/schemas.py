"""The structured-output contract CodeEvaluationProvider implementations
must return (module §10, §11).

**Gemini structured-output constraint** — the same rule
app/services/resume_intelligence/schemas.py and
app/services/interview_intelligence/schemas.py were written under from
the start (see either module's matching note for the bug this guards
against): no field below may have a non-None default. `X | None = None`
and `Field(default_factory=list)` are safe; `Field(default=<anything but
None>)` is not.

Deliberately excludes `correctness_score`/`overall_code_score` — those are
computed deterministically (execution results; a weighted combination of
these sub-scores, respectively — see CodingRoundService), never asked of
the model. No chain-of-thought (module §20): every field is a score, a
short evidence-citing explanation, or a structured list — nothing here
asks for the model's internal reasoning.
"""

from pydantic import BaseModel, Field


class CodeEvaluationResult(BaseModel):
    readability_score: float = Field(description="0-100")
    readability_explanation: str
    optimization_score: float = Field(description="0-100")
    optimization_explanation: str
    edge_case_score: float = Field(
        description="0-100 — how well the submitted approach handles edge cases (empty "
        "input, boundary values, duplicates, etc.), based on reading the code, not on "
        "which hidden tests happened to be included"
    )
    edge_case_explanation: str
    time_complexity: str = Field(
        description="Big-O estimate of the submitted approach, e.g. 'O(n log n)' — descriptive"
    )
    space_complexity: str = Field(
        description="Big-O estimate, e.g. 'O(n)' — descriptive, not a score"
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Concrete, specific strengths of this submission — never generic praise",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Concrete, specific weaknesses — never invented if the code has none",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Concrete, actionable suggestions for improving this exact submission",
    )
