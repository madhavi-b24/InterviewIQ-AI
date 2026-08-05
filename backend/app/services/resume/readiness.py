"""Role-readiness + explainable interview-difficulty recommendation
(module §11, §12).

Both functions are pure, deterministic, and take plain data (skill name
strings, project/experience text blobs) rather than ORM objects — no
LLM call, no DB session — so they're trivially unit-testable and the
"not an arbitrary LLM guess" requirement is structural, not a prompting
convention. ResumeService assembles the inputs from persisted rows and
persists the outputs back onto resume_gap_analysis.
"""

from dataclasses import dataclass, field

from app.models.enums import DifficultyLevel
from app.services.resume.role_profiles import RoleProfile

# Presence of these phrases in a project/experience description or
# evidence text is treated as a signal of production/scale complexity —
# deliberately coarse keyword matching, not an LLM judgment call.
_COMPLEXITY_KEYWORDS = (
    "scaled",
    "scalable",
    "distributed",
    "optimi",  # optimize/optimide/optimization
    "architect",
    "concurrency",
    "concurrent",
    "production",
    "microservice",
    "high-throughput",
    "high throughput",
    "fault-toleran",
    "fault toleran",
    "latency",
    "kubernetes",
    "ci/cd",
    "load balanc",
    "real-time",
    "real time",
    "asynchronous",
    "million",
    "thousand users",
    "requests/sec",
    "requests per second",
)


@dataclass(slots=True)
class RoleReadinessResult:
    matching_skills: list[str]
    missing_skills: list[str]
    strengths: list[str]
    focus_areas: list[str]


@dataclass(slots=True)
class DifficultyRecommendation:
    level: DifficultyLevel
    confidence: float  # 0-100
    reasons: list[str] = field(default_factory=list)


def compute_role_readiness(
    *, canonical_skills: list[str], role_profile: RoleProfile
) -> RoleReadinessResult:
    owned = {skill.lower() for skill in canonical_skills}
    required = role_profile.required_skills
    nice_to_have = role_profile.nice_to_have_skills

    matching = [skill for skill in required if skill.lower() in owned]
    missing = [skill for skill in required if skill.lower() not in owned]
    strengths = [skill for skill in nice_to_have if skill.lower() in owned]

    focus_areas = list(missing)
    if not focus_areas:
        # Nothing required is missing — point at the next tier of growth
        # instead of leaving focus_areas empty.
        focus_areas = [skill for skill in nice_to_have if skill.lower() not in owned][:5]

    return RoleReadinessResult(
        matching_skills=matching,
        missing_skills=missing,
        strengths=strengths,
        focus_areas=focus_areas,
    )


def compute_interview_level(
    *,
    canonical_skills: list[str],
    project_texts: list[str],
    experience_texts: list[str],
    role_profile: RoleProfile,
) -> DifficultyRecommendation:
    reasons: list[str] = []
    owned = {skill.lower() for skill in canonical_skills}
    required = role_profile.required_skills

    matched_required = sum(1 for skill in required if skill.lower() in owned)
    breadth_ratio = (matched_required / len(required)) if required else 0.0
    reasons.append(
        f"Matches {matched_required}/{len(required)} core skills for {role_profile.label}"
    )

    project_count = len(project_texts)
    experience_count = len(experience_texts)
    depth_ratio = min(1.0, project_count * 0.25 + experience_count * 0.35)
    reasons.append(
        f"{project_count} project(s) and {experience_count} work-experience entry/entries "
        "found on the resume"
    )

    complexity_hits = _count_complexity_keywords(project_texts + experience_texts)
    complexity_ratio = min(1.0, complexity_hits / 3)
    if complexity_hits:
        reasons.append(
            f"Found {complexity_hits} indicator(s) of production/scale complexity "
            "(e.g. distributed, optimized, scaled, production)"
        )

    score = 0.45 * breadth_ratio + 0.30 * depth_ratio + 0.25 * complexity_ratio
    if score < 0.35:
        level = DifficultyLevel.EASY
    elif score < 0.70:
        level = DifficultyLevel.MEDIUM
    else:
        level = DifficultyLevel.HARD
    reasons.append(
        f"Composite readiness score {round(score * 100)}/100 -> recommended level: {level.value}"
    )

    # Confidence reflects how much resume material there was to reason
    # over, independent of the score itself — a sparse resume that
    # happens to score "medium" should still be reported as low-confidence.
    data_points = len(canonical_skills) + project_count * 2 + experience_count * 2
    confidence = min(95.0, 30.0 + data_points * 3.0)
    if data_points < 3:
        confidence = min(confidence, 45.0)
        reasons.append("Limited resume detail available — confidence is reduced")

    return DifficultyRecommendation(level=level, confidence=round(confidence, 2), reasons=reasons)


def _count_complexity_keywords(texts: list[str]) -> int:
    blob = " ".join(text for text in texts if text).lower()
    return sum(1 for keyword in _COMPLEXITY_KEYWORDS if keyword in blob)
