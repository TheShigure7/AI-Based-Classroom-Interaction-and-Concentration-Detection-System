"""Schemas for analytics overview APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.schemas.records import SessionOptionPayload
from app.models.schemas.realtime import SummaryPayload


class AnalyticsEventItemPayload(BaseModel):
    """One event type aggregate card/item."""

    event_type: str
    label: str
    count: int
    rate: float


class AnalyticsTrendPointPayload(BaseModel):
    """One daily trend point."""

    date: str
    label: str
    count: int


class AnalyticsHourPointPayload(BaseModel):
    """One hourly distribution point."""

    hour: int
    label: str
    count: int


class AnalyticsSessionSummaryPayload(BaseModel):
    """One recent session summary row."""

    session_id: str
    started_at: str | None = None
    status: str
    video_source: str
    alert_count: int = 0
    last_alert_at: str | None = None
    top_event_type: str | None = None
    risk_score: int = 0


class AnalyticsOverviewResponse(BaseModel):
    """Aggregated analytics response for the analytics page."""

    generated_at: str
    days: int
    selected_session_id: str | None = None
    current_summary: SummaryPayload = Field(default_factory=SummaryPayload)
    total_sessions: int = 0
    total_alerts: int = 0
    unique_students: int = 0
    event_breakdown: list[AnalyticsEventItemPayload] = Field(default_factory=list)
    daily_trend: list[AnalyticsTrendPointPayload] = Field(default_factory=list)
    hourly_distribution: list[AnalyticsHourPointPayload] = Field(default_factory=list)
    recent_sessions: list[AnalyticsSessionSummaryPayload] = Field(default_factory=list)
    sessions: list[SessionOptionPayload] = Field(default_factory=list)
