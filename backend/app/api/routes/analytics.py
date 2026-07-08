"""Analytics routes for historical classroom summaries."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.models.schemas.analytics import AnalyticsOverviewResponse
from app.services.runtime import runtime


router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    session_id: str | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=30),
) -> AnalyticsOverviewResponse:
    """Return aggregated analytics for the analytics page."""
    return runtime.get_analytics_overview(
        session_id=session_id,
        days=days,
    )
