"""Request/response DTOs for the report/roadmap API (Module 7). Field
names for ReportOut's `overall`/`sections`/`weak_areas`/`strong_areas`/
`summary` follow API.md §6's response shape exactly, written before this
module existed — kept as-is rather than redesigned. One addition beyond
that sketch: `ReportOut.id`, since `GET /reports/{report_id}/roadmap`
needs a report_id the client has no other way to discover from the report
response alone.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ResourceType, Severity


class ScoreExplanationOut(BaseModel):
    score: float
    explanation: str


class WeakAreaOut(BaseModel):
    topic: str
    severity: Severity
    evidence: str


class StrongAreaOut(BaseModel):
    topic: str
    evidence: str


class ReportOut(BaseModel):
    id: uuid.UUID
    overall: ScoreExplanationOut
    sections: dict[str, ScoreExplanationOut]
    weak_areas: list[WeakAreaOut]
    strong_areas: list[StrongAreaOut]
    summary: str


class RoadmapItemOut(BaseModel):
    id: uuid.UUID
    topic: str
    resource_title: str
    resource_url: str | None
    resource_type: ResourceType
    priority: int
    sequence_no: int
    is_completed: bool


class RoadmapOut(BaseModel):
    id: uuid.UUID
    generated_at: datetime
    items: list[RoadmapItemOut]


class RoadmapItemUpdateRequest(BaseModel):
    is_completed: bool
