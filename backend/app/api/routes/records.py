"""Persisted records routes for the records page."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas.records import RecordDeleteResponse, RecordsListResponse
from app.services.runtime import runtime


router = APIRouter(prefix="/api/v1/records", tags=["records"])


@router.get("", response_model=RecordsListResponse)
def list_records(
    event_type: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> RecordsListResponse:
    """Return persisted alert records with lightweight filters."""
    return runtime.list_records(
        event_type=event_type,
        session_id=session_id,
        limit=limit,
    )


@router.delete("/{alert_id}", response_model=RecordDeleteResponse)
def delete_record(alert_id: str) -> RecordDeleteResponse:
    """Delete one persisted alert record."""
    response = runtime.delete_record(alert_id)
    if not response.success:
        raise HTTPException(status_code=404, detail="record not found")
    return response
