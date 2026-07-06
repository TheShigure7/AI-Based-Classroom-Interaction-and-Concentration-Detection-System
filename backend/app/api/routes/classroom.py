"""Realtime classroom routes for the web frontend."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.models.schemas.realtime import ClassroomCurrentResponse
from app.services.runtime import runtime


router = APIRouter(tags=["classroom"])


@router.get("/api/v1/classroom/current", response_model=ClassroomCurrentResponse)
def get_current_classroom_state() -> ClassroomCurrentResponse:
    """Return the current classroom state for the realtime page."""
    return runtime.get_current_state()


@router.get("/api/v1/video/stream")
def stream_classroom_video() -> StreamingResponse:
    """Return the latest monitored video output as an MJPEG stream."""
    return StreamingResponse(
        runtime.mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/api/v1/alerts/{alert_id}/image")
def get_alert_snapshot(alert_id: str) -> Response:
    """Return the image snapshot for one in-memory alert."""
    snapshot = runtime.get_alert_snapshot(alert_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="alert snapshot not found")
    return Response(content=snapshot, media_type="image/jpeg")
