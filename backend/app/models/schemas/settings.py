"""Schemas for lightweight frontend settings APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VideoSourceOption(BaseModel):
    """Saved video source option for the settings page."""

    label: str
    value: str


class SettingsPayload(BaseModel):
    """Runtime-editable settings exposed to the frontend."""

    local_camera_source: str = "0"
    network_video_source: str = ""
    recent_video_sources: list[VideoSourceOption] = Field(default_factory=list)
    enable_pose_analysis: bool = True
    enable_sleeping_detection: bool = True
    enable_talking_detection: bool = True
    low_attention_threshold: int = 60
    save_alert_snapshots: bool = True
    enable_realtime_alerts: bool = True
    enable_daily_summary: bool = False
    enable_email_summary: bool = False
    email_address: str = ""
    alert_snapshot_dir: str = "data/alerts"


class UpdateSettingsRequest(BaseModel):
    """Request body for updating lightweight frontend settings."""

    local_camera_source: str | None = None
    network_video_source: str | None = None
    enable_pose_analysis: bool | None = None
    enable_sleeping_detection: bool | None = None
    enable_talking_detection: bool | None = None
    low_attention_threshold: int | None = None
    save_alert_snapshots: bool | None = None
    enable_realtime_alerts: bool | None = None
    enable_daily_summary: bool | None = None
    enable_email_summary: bool | None = None
    email_address: str | None = None
    alert_snapshot_dir: str | None = None
