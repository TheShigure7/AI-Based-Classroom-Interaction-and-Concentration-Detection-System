"""FastAPI application entry point for the classroom analysis system."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.classroom import router as classroom_router
from app.api.routes.session import router as session_router
from app.api.websocket.realtime import router as realtime_ws_router


app = FastAPI(
    title="AI Classroom Interaction Monitor",
    version="0.1.0",
    description="Minimal backend for camera-based classroom analysis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session_router)
app.include_router(classroom_router)
app.include_router(realtime_ws_router)


@app.get("/api/v1/health")
def health_check() -> dict[str, str]:
    """Simple health endpoint for startup validation."""
    return {"status": "ok"}
