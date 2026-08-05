"""Importing this package registers every model on Base.metadata — this is
what Alembic's env.py imports for autogenerate, and what makes cross-file
string relationships (e.g. "Role") resolvable at mapper-configuration time.

Add new model modules to this list, don't rely on side-effect import order.
"""

from app.db.base import Base
from app.models.evaluation import AnswerEvaluation, CodingEvaluation
from app.models.interview import (
    Answer,
    CodeSubmission,
    CodeSubmissionTestResult,
    InterviewRound,
    InterviewSession,
    Question,
    QuestionTestCase,
)
from app.models.planning import Company, InterviewTemplate, Role, TemplateRound
from app.models.progress import CompanyReadiness, SkillProgress, UserProgressSnapshot
from app.models.report import (
    InterviewReport,
    LearningRoadmap,
    ReportSectionScore,
    ReportStrongArea,
    ReportWeakArea,
    RoadmapItem,
)
from app.models.resume import (
    Resume,
    ResumeAchievement,
    ResumeCertification,
    ResumeEducation,
    ResumeExperience,
    ResumeGapAnalysis,
    ResumeProject,
    ResumeSkill,
)
from app.models.user import PasswordResetToken, RefreshToken, User

__all__ = [
    "Base",
    "User",
    "RefreshToken",
    "PasswordResetToken",
    "Resume",
    "ResumeSkill",
    "ResumeProject",
    "ResumeExperience",
    "ResumeEducation",
    "ResumeCertification",
    "ResumeAchievement",
    "ResumeGapAnalysis",
    "Company",
    "Role",
    "InterviewTemplate",
    "TemplateRound",
    "InterviewSession",
    "InterviewRound",
    "Question",
    "QuestionTestCase",
    "Answer",
    "CodeSubmission",
    "CodeSubmissionTestResult",
    "AnswerEvaluation",
    "CodingEvaluation",
    "InterviewReport",
    "ReportSectionScore",
    "ReportWeakArea",
    "ReportStrongArea",
    "LearningRoadmap",
    "RoadmapItem",
    "SkillProgress",
    "CompanyReadiness",
    "UserProgressSnapshot",
]
