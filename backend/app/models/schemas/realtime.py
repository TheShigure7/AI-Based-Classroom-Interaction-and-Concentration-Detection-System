"""Schemas for realtime classroom monitoring APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SessionStatus = Literal["idle", "running", "paused", "stopped", "error"]
EventType = Literal[
    "hand_raised",
    "head_down",
    "phone_risk",
    "sleeping",
    "talking_risk",
    "low_attention",
]


class StartSessionRequest(BaseModel):
    """Request body for starting a classroom monitoring session."""

    video_source: str = Field(default="0")
    enable_pose_analysis: bool = Field(default=True)
    save_alert_snapshots: bool = Field(default=True)


class SessionPayload(BaseModel):
    """Common session metadata returned by session endpoints."""

    session_id: str
    status: SessionStatus
    video_source: str
    started_at: str | None = None
    stopped_at: str | None = None
    duration_seconds: int = 0
    enable_pose_analysis: bool = True
    save_alert_snapshots: bool = True
    last_error: str = ""


class SessionActionResponse(BaseModel):
    """Response body for session start/stop endpoints."""

    success: bool
    message: str
    session: SessionPayload


class ResolutionPayload(BaseModel):
    """Current runtime resolution."""

    width: int
    height: int


class PerformancePayload(BaseModel):
    """Current runtime performance metrics."""

    inference_fps: float = 0.0
    display_fps: float = 0.0


class BehaviorCountsPayload(BaseModel):
    """Current behavior counts."""

    hand_raised: int = 0
    head_down: int = 0
    phone_risk: int = 0
    sleeping: int = 0
    talking_risk: int = 0


class BehaviorRatesPayload(BaseModel):
    """Current behavior rates."""

    hand_raised: float = 0.0
    head_down: float = 0.0
    phone_risk: float = 0.0
    sleeping: float = 0.0
    talking_risk: float = 0.0


class SummaryPayload(BaseModel):
    """Current classroom summary metrics."""

    student_count: int = 0
    average_attention: int = 0
    low_attention_count: int = 0
    behavior_counts: BehaviorCountsPayload = Field(default_factory=BehaviorCountsPayload)
    behavior_rates: BehaviorRatesPayload = Field(default_factory=BehaviorRatesPayload)


class BBoxPayload(BaseModel):
    """Serialized bounding box."""

    x1: int
    y1: int
    x2: int
    y2: int


class StudentStatesPayload(BaseModel):
    """Per-student behavior flags."""

    hand_raised: bool = False
    head_down: bool = False
    phone_risk: bool = False
    sleeping: bool = False
    talking_risk: bool = False


class StudentPayload(BaseModel):
    """Serialized current student state."""

    student_id: str
    track_id: str
    bbox: BBoxPayload
    attention_score: int
    is_low_attention: bool
    states: StudentStatesPayload


class AlertPayload(BaseModel):
    """Serialized alert card for the realtime page."""

    alert_id: str
    timestamp: str
    student_id: str
    event_type: EventType
    attention_score: int
    snapshot_url: str


class ClassroomCurrentResponse(BaseModel):
    """Current classroom state returned to the realtime page."""

    running: bool
    session_id: str
    status: SessionStatus
    video_source: str
    duration_seconds: int
    last_error: str = ""
    resolution: ResolutionPayload
    performance: PerformancePayload
    summary: SummaryPayload
    students: list[StudentPayload] = Field(default_factory=list)
    latest_alerts: list[AlertPayload] = Field(default_factory=list)


class RealtimeEvent(BaseModel):
    """WebSocket event payload for realtime updates."""

    type: Literal["classroom_update"]
    timestamp: str
    session_id: str
    status: SessionStatus
    duration_seconds: int
    performance: PerformancePayload
    summary: SummaryPayload
    latest_alerts: list[AlertPayload] = Field(default_factory=list)
