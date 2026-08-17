"""Request/response DTOs for the interview-planning catalog API
(API.md §3, Module 4). Read-only, candidate-facing browse surface —
companies/roles/templates, filtered to `is_active` at the repository layer.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import DifficultyLevel, InterviewMode, RoleLevel, RoundType


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    logo_url: str | None
    interview_style_notes: str | None


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    title: str
    level: RoleLevel
    description: str | None
    role_key: str | None


class TemplateRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    round_type: RoundType
    sequence_no: int
    weight: Decimal
    is_required: bool
    difficulty_override: DifficultyLevel | None


class TemplateSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    role_id: uuid.UUID
    name: str
    description: str | None
    mode: InterviewMode
    default_difficulty: DifficultyLevel


class TemplateDetailOut(TemplateSummaryOut):
    rounds: list[TemplateRoundOut]
    created_at: datetime
