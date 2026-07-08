"""SQLite connection helpers for the classroom monitor."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

from app.db.base import DEFAULT_DB_PATH, ensure_runtime_directories


def initialize_database() -> None:
    """Create all required SQLite tables if they do not exist yet."""
    ensure_runtime_directories()
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS video_sources (
                value TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                last_used_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS detection_sessions (
                session_id TEXT PRIMARY KEY,
                video_source TEXT NOT NULL,
                started_at TEXT,
                stopped_at TEXT,
                status TEXT NOT NULL,
                enable_pose_analysis INTEGER NOT NULL,
                save_alert_snapshots INTEGER NOT NULL,
                last_error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS alert_records (
                alert_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                student_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                attention_score INTEGER NOT NULL,
                snapshot_path TEXT NOT NULL
            );
            """
        )
        connection.commit()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield one SQLite connection with row access enabled."""
    ensure_runtime_directories()
    connection = sqlite3.connect(DEFAULT_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()
