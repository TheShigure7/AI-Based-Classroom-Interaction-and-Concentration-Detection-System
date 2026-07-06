"""Session control routes for realtime classroom monitoring."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas.realtime import SessionActionResponse, SessionPayload, StartSessionRequest
from app.services.runtime import runtime


router = APIRouter(prefix="/api/v1/session", tags=["session"])


@router.post("/start", response_model=SessionActionResponse)
def start_session(request: StartSessionRequest) -> SessionActionResponse:
    """Start the classroom monitoring session."""
    return runtime.start_session(request)


@router.post("/stop", response_model=SessionActionResponse)
def stop_session() -> SessionActionResponse:
    """Stop the current classroom monitoring session."""
    return runtime.stop_session()


@router.get("/status", response_model=SessionPayload)
def get_session_status() -> SessionPayload:
    """Return current session metadata."""
    return runtime.get_session_status()
