"""System-level routes such as controlled app shutdown."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.runtime import runtime


router = APIRouter(prefix="/api/v1/app", tags=["system"])


@router.post("/exit")
def exit_application() -> dict[str, bool]:
    """Request the backend process to terminate shortly after responding."""
    runtime.request_application_exit()
    return {"success": True}
