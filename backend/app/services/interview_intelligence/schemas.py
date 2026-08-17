"""The structured-output contracts every InterviewAgentProvider
implementation must return (Module 5 — Architecture.md §5.1).

Mirrors app/services/resume_intelligence/schemas.py's role for the resume
pipeline: the *only* place that defines what each agent's Gemini call
returns. GeminiInterviewAgentProvider passes these as Gemini's
`response_schema` (structured output); FakeInterviewAgentProvider
constructs the same models by hand. No node ever sees raw LLM JSON.

**Gemini structured-output constraint** — carried over from the bug fixed
earlier in Resume Intelligence (see
app/services/resume_intelligence/schemas.py's matching note for the full
explanation): no field below may have a non-None default. `X | None =
None` and `Field(default_factory=list)` are safe; `Field(default=<anything
but None>)` is not — google-genai's client-side schema converter rejects
it. Every field here was written with that rule in mind from the start,
not fixed after the fact.

**No chain-of-thought** (module §20): every field is a score, a short
evidence-citing explanation, or a structured flag — nothing here asks the
model for its internal reasoning/deliberation, and none of these fields
should ever be echoed as "how the model thought about it."
"""

from pydantic import BaseModel, Field


class GeneratedQuestion(BaseModel):
    """Output of both the Question Generator Agent (a fresh, round-opening
    question) and the Interview Agent (a follow-up to the answer just
    given) — same shape, different prompt framing and caller (module §7,
    §8). Kept as one schema since both are "the next thing the interviewer
    says," not two different kinds of data.
    """

    question_text: str = Field(
        description=(
            "The interviewer's next spoken question — concise, one question only, no preamble"
        )
    )
    topic: str = Field(
        description=(
            "Short topic label for this question, e.g. 'hash tables', 'React state management'"
        )
    )
    grounded_in_resume: bool = Field(
        description=(
            "True only if this question references a specific skill/project/experience "
            "actually present in the provided resume evidence — never a claim not backed by it"
        )
    )


class TechnicalEvaluation(BaseModel):
    """Evaluation Agent output (module §9) — technical correctness and
    problem solving only. Coding correctness/readability/optimization are
    Module 6's CodingEvaluation, out of scope here. Never a single bare
    score — every score is paired with its explanation, matching this
    project's schema-wide convention.
    """

    technical_score: float = Field(description="0-100")
    technical_explanation: str
    problem_solving_score: float = Field(description="0-100")
    problem_solving_explanation: str
    missing_concepts: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    follow_up_worthy: bool = Field(
        description=(
            "True only if there is one specific, concrete reason to probe deeper on this "
            "exact answer (an incomplete claim, an interesting or incorrect claim worth "
            "testing, a shallow explanation) rather than moving on to a new topic"
        )
    )
    follow_up_reason: str | None = Field(
        default=None,
        description=(
            "One short sentence naming the specific reason — required if follow_up_worthy is true"
        ),
    )


class CommunicationEvaluation(BaseModel):
    """Communication Agent output (module §11). Scores only observable
    communication qualities — clarity, structure, conciseness, terminology
    usage, ability to explain reasoning. Never a psychological trait,
    personality, mental state, or gender inference (module §9, §11
    explicit prohibition). 'confidence' here is the DB/report vocabulary
    this project already uses (answer_evaluations.confidence_score,
    Database.md §6) redefined precisely: the observable
    directness/assertiveness of the candidate's *phrasing* (hedging vs.
    direct language, decisiveness of explanation) — never an inference
    about how the candidate actually feels.
    """

    communication_score: float = Field(description="0-100")
    communication_explanation: str
    confidence_score: float = Field(
        description=(
            "0-100 — observable clarity/directness of phrasing only "
            "(e.g. hedging language vs. decisive explanation), never a psychological inference"
        )
    )
    confidence_explanation: str
