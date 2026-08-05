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
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    TIMEOUT = "timeout"


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
