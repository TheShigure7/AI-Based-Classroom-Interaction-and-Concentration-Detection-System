"""Schemas for persisted classroom records APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecordItemPayload(BaseModel):
    """One persisted alert record shown on the records page."""

    alert_id: str
    session_id: str
    timestamp: str
    student_id: str
    event_type: str
    attention_score: int
    snapshot_url: str


class SessionOptionPayload(BaseModel):
    """One detection session option used for records filtering."""

    session_id: str
    started_at: str | None = None
    video_source: str
    status: str


class RecordsListResponse(BaseModel):
    """Response payload for the records page."""

    total: int
    items: list[RecordItemPayload] = Field(default_factory=list)
    sessions: list[SessionOptionPayload] = Field(default_factory=list)
