"""FastAPI application entry point for the classroom analysis system."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.analytics import router as analytics_router
from app.api.routes.classroom import router as classroom_router
from app.api.routes.records import router as records_router
from app.api.routes.session import router as session_router
from app.api.routes.settings import router as settings_router
from app.api.routes.system import router as system_router
from app.api.websocket.realtime import router as realtime_ws_router


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"


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
app.include_router(analytics_router)
app.include_router(records_router)
app.include_router(settings_router)
app.include_router(system_router)
app.include_router(realtime_ws_router)


@app.get("/api/v1/health")
def health_check() -> dict[str, str]:
    """Simple health endpoint for startup validation."""
    return {"status": "ok"}


if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="frontend-assets")


@app.get("/", include_in_schema=False)
def frontend_index():
    """Serve the built frontend homepage when available."""
    if FRONTEND_DIST_DIR.joinpath("index.html").exists():
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
    return HTMLResponse(
        "<h3>Frontend build not found.</h3><p>Please run <code>npm run build</code> in the frontend directory.</p>",
        status_code=503,
    )


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_spa_fallback(full_path: str):
    """Serve built SPA routes without interfering with API or websocket paths."""
    if full_path.startswith(("api/", "ws/", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="Not found")

    requested_path = FRONTEND_DIST_DIR / full_path
    if requested_path.is_file():
        return FileResponse(requested_path)

    if FRONTEND_DIST_DIR.joinpath("index.html").exists():
        return FileResponse(FRONTEND_DIST_DIR / "index.html")

    raise HTTPException(status_code=404, detail="Frontend build not found")
