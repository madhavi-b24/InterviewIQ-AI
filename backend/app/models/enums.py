"""All Postgres ENUM types, one Python StrEnum per `<table>_<column>_enum`
in Database.md. Centralized here (rather than inline per model) so the
same enum can be shared across tables that reuse a concept, e.g.
DifficultyLevel appears on resumes, templates, sessions, and questions.
"""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[StrEnum], *, name: str) -> SAEnum:
    """Native Postgres ENUM using each member's lowercase `.value`
    ("local", "google", ...) as the stored label — matching Database.md —
    instead of SQLAlchemy's default of the Python member `.name`
    ("LOCAL", "GOOGLE", ...).
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda cls: [m.value for m in cls])


class AuthProvider(StrEnum):
    LOCAL = "local"
    GOOGLE = "google"


class UserRole(StrEnum):
    CANDIDATE = "candidate"
    RECRUITER = "recruiter"
    ADMIN = "admin"


class ProficiencyHint(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class SkillSource(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class SkillCategory(StrEnum):
    """Module 3 — resume_skills.category. Deliberately coarse and fixed in
    code (not the maintainable alias layer — see
    app/services/resume/skill_normalization.py) because these are report/UI
    buckets, not the thing that grows as new technologies appear.
    """

    PROGRAMMING_LANGUAGE = "programming_language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    CLOUD = "cloud"
    AI_ML = "ai_ml"
    DEVELOPER_TOOL = "developer_tool"
    OTHER = "other"


class ParsedStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class DifficultyLevel(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class RoleLevel(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"


class RoundType(StrEnum):
    INTRODUCTION = "introduction"
    TECHNICAL = "technical"
    CODING = "coding"
    BEHAVIORAL = "behavioral"
    SYSTEM_DESIGN = "system_design"
    RESUME_DISCUSSION = "resume_discussion"
    FINAL = "final"


class SessionStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class RoundStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class QuestionType(StrEnum):
    MCQ = "mcq"
    OPEN = "open"
    CODING = "coding"
    SYSTEM_DESIGN = "system_design"


class QuestionSource(StrEnum):
    BANK = "bank"
    GENERATED = "generated"


class CodeExecutionStatus(StrEnum):
    """Module 1 baseline: QUEUED/RUNNING (submission lifecycle),
    SUCCESS/PARTIAL (aggregate outcome), ERROR/TIMEOUT (generic failure).
    Module 6 extends the failure states with the specific reasons module
    §7 asks for — COMPILE_ERROR/RUNTIME_ERROR/MEMORY_LIMIT/OUTPUT_LIMIT
    are new; TIME_LIMIT reuses the existing TIMEOUT value (same concept,
    no need for a near-duplicate), and EXECUTION_ERROR reuses the
    existing generic ERROR value — see docs/Database.md §5 for the full
    mapping. Additive only: no existing value's meaning changed.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"  # = module §7's EXECUTION_ERROR
    TIMEOUT = "timeout"  # = module §7's TIME_LIMIT
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    MEMORY_LIMIT = "memory_limit"
    OUTPUT_LIMIT = "output_limit"


class DifficultySignal(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    MAINTAIN = "maintain"


class ReportSection(StrEnum):
    TECHNICAL = "technical"
    CODING = "coding"
    COMMUNICATION = "communication"
    PROBLEM_SOLVING = "problem_solving"
    CONFIDENCE = "confidence"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResourceType(StrEnum):
    ARTICLE = "article"
    VIDEO = "video"
    COURSE = "course"
    PRACTICE = "practice"


class ProgressTrend(StrEnum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class InterviewMode(StrEnum):
    """Module 4 — candidate-selectable interview shape. Primarily a tag on
    `interview_templates.mode` (which rounds a template represents) that a
    plan request either inherits or must match exactly — modes never
    dynamically filter a template's rounds at plan time, keeping round
    selection entirely data-driven per Architecture.md's "don't hardcode
    workflow order in agents" rule.
    """

    FULL_MOCK = "full_mock"
    TECHNICAL_ONLY = "technical_only"
    CODING_ONLY = "coding_only"
    BEHAVIORAL_ONLY = "behavioral_only"
    RESUME_DEEP_DIVE = "resume_deep_dive"


class RequestedDifficulty(StrEnum):
    """Module 4 — what the candidate asked for at plan time.

    Distinct from DifficultyLevel: adds AUTO, which resolves deterministically
    (never via an LLM call) to a DifficultyLevel — see
    app/services/planning/interview_planner.py. `interview_sessions.starting_difficulty`
    stores the resolved value; `interview_sessions.requested_difficulty` stores
    this raw preference, so a report can always show what the candidate asked
    for vs. what was actually used.
    """

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    AUTO = "auto"
