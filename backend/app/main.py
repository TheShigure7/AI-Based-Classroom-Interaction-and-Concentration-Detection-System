"""FastAPI application entry point for the classroom analysis system."""

from __future__ import annotations

from fastapi import FastAPI


app = FastAPI(
    title="AI Classroom Interaction Monitor",
    version="0.1.0",
    description="Minimal backend for camera-based classroom analysis.",
)


@app.get("/api/v1/health")
def health_check() -> dict[str, str]:
    """Simple health endpoint for startup validation."""
    return {"status": "ok"}
