"""Settings routes for the first-phase frontend."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas.settings import SettingsPayload, UpdateSettingsRequest
from app.services.runtime import runtime


router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=SettingsPayload)
def get_settings() -> SettingsPayload:
    """Return current lightweight frontend settings."""
    return runtime.get_settings()


@router.put("", response_model=SettingsPayload)
def update_settings(request: UpdateSettingsRequest) -> SettingsPayload:
    """Update current lightweight frontend settings."""
    return runtime.update_settings(request)
