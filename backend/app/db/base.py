"""SQLite database bootstrap helpers."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DB_DIR = DATA_DIR / "db"
ALERTS_DIR = DATA_DIR / "alerts"
DEFAULT_DB_PATH = DB_DIR / "classroom_monitor.db"


def ensure_runtime_directories() -> None:
    """Create local runtime data directories when missing."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
