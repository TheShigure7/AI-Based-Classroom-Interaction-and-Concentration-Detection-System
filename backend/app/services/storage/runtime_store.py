"""SQLite-backed persistence for settings, sessions, and alerts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.db.base import ALERTS_DIR, PROJECT_ROOT
from app.db.session import get_connection, initialize_database
from app.models.schemas.analytics import (
    AnalyticsEventItemPayload,
    AnalyticsHourPointPayload,
    AnalyticsSessionSummaryPayload,
    AnalyticsTrendPointPayload,
)
from app.models.schemas.records import RecordItemPayload, SessionOptionPayload
from app.models.schemas.settings import SettingsPayload, VideoSourceOption


@dataclass
class StoredAlertRecord:
    """Persisted alert record metadata."""

    alert_id: str
    session_id: str
    timestamp: str
    student_id: str
    event_type: str
    attention_score: int
    snapshot_path: str


class RuntimeStore:
    """Storage service for lightweight runtime persistence."""

    EVENT_LABELS = {
        "hand_raised": "举手",
        "head_down": "低头",
        "phone_risk": "手机风险",
        "sleeping": "睡觉风险",
        "talking_risk": "疑似交谈",
        "low_attention": "低专注",
    }

    SETTINGS_KEYS = (
        "local_camera_source",
        "network_video_source",
        "enable_pose_analysis",
        "enable_sleeping_detection",
        "enable_talking_detection",
        "low_attention_threshold",
        "save_alert_snapshots",
        "enable_realtime_alerts",
        "enable_daily_summary",
        "enable_email_summary",
        "email_address",
        "alert_snapshot_dir",
    )

    def __init__(self) -> None:
        initialize_database()

    @staticmethod
    def default_alert_snapshot_dir() -> str:
        """Return the default relative snapshot directory shown in settings."""
        return str(ALERTS_DIR.relative_to(PROJECT_ROOT))

    def load_settings(self, defaults: SettingsPayload) -> SettingsPayload:
        """Load persisted settings and recent video sources."""
        settings = defaults.model_copy(deep=True)
        with get_connection() as connection:
            rows = connection.execute("SELECT key, value FROM app_settings").fetchall()
            for row in rows:
                key = row["key"]
                if key not in self.SETTINGS_KEYS:
                    continue
                setattr(settings, key, json.loads(row["value"]))

            source_rows = connection.execute(
                """
                SELECT label, value
                FROM video_sources
                ORDER BY last_used_at DESC
                LIMIT 8
                """
            ).fetchall()
            settings.recent_video_sources = [
                VideoSourceOption(label=row["label"], value=row["value"])
                for row in source_rows
            ] or settings.recent_video_sources

        return settings

    def save_settings(self, settings: SettingsPayload) -> None:
        """Persist current settings to SQLite."""
        with get_connection() as connection:
            for key in self.SETTINGS_KEYS:
                connection.execute(
                    """
                    INSERT INTO app_settings (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, json.dumps(getattr(settings, key), ensure_ascii=False)),
                )
            connection.commit()

    def remember_video_source(self, value: str, label: str, used_at: str) -> None:
        """Persist one recent video source item."""
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO video_sources (value, label, last_used_at)
                VALUES (?, ?, ?)
                ON CONFLICT(value) DO UPDATE SET
                    label = excluded.label,
                    last_used_at = excluded.last_used_at
                """,
                (value, label, used_at),
            )
            connection.commit()

    def upsert_session(
        self,
        session_id: str,
        video_source: str,
        started_at: str | None,
        stopped_at: str | None,
        status: str,
        enable_pose_analysis: bool,
        save_alert_snapshots: bool,
        last_error: str,
    ) -> None:
        """Create or update one detection session record."""
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO detection_sessions (
                    session_id,
                    video_source,
                    started_at,
                    stopped_at,
                    status,
                    enable_pose_analysis,
                    save_alert_snapshots,
                    last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    video_source = excluded.video_source,
                    started_at = excluded.started_at,
                    stopped_at = excluded.stopped_at,
                    status = excluded.status,
                    enable_pose_analysis = excluded.enable_pose_analysis,
                    save_alert_snapshots = excluded.save_alert_snapshots,
                    last_error = excluded.last_error
                """,
                (
                    session_id,
                    video_source,
                    started_at,
                    stopped_at,
                    status,
                    int(enable_pose_analysis),
                    int(save_alert_snapshots),
                    last_error,
                ),
            )
            connection.commit()

    def save_alert_record(self, record: StoredAlertRecord) -> None:
        """Persist one alert record metadata row."""
        with get_connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO alert_records (
                    alert_id,
                    session_id,
                    timestamp,
                    student_id,
                    event_type,
                    attention_score,
                    snapshot_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.alert_id,
                    record.session_id,
                    record.timestamp,
                    record.student_id,
                    record.event_type,
                    record.attention_score,
                    record.snapshot_path,
                ),
            )
            connection.commit()

    def get_alert_snapshot_path(self, alert_id: str) -> str | None:
        """Return persisted alert snapshot path by ID."""
        with get_connection() as connection:
            row = connection.execute(
                "SELECT snapshot_path FROM alert_records WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["snapshot_path"])

    def delete_alert_record(self, alert_id: str) -> str | None:
        """Delete one persisted alert record and return its snapshot path if found."""
        with get_connection() as connection:
            row = connection.execute(
                "SELECT snapshot_path FROM alert_records WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "DELETE FROM alert_records WHERE alert_id = ?",
                (alert_id,),
            )
            connection.commit()
        return str(row["snapshot_path"])

    def list_alert_records(
        self,
        *,
        event_type: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[RecordItemPayload]:
        """Return persisted alert records ordered by newest first."""
        filters: list[str] = []
        params: list[object] = []

        if event_type:
            filters.append("event_type = ?")
            params.append(event_type)
        if session_id:
            filters.append("session_id = ?")
            params.append(session_id)

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"""
            SELECT alert_id, session_id, timestamp, student_id, event_type, attention_score
            FROM alert_records
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        with get_connection() as connection:
            rows = connection.execute(query, params).fetchall()

        return [
            RecordItemPayload(
                alert_id=row["alert_id"],
                session_id=row["session_id"],
                timestamp=row["timestamp"],
                student_id=row["student_id"],
                event_type=row["event_type"],
                attention_score=int(row["attention_score"]),
                snapshot_url=f"/api/v1/alerts/{row['alert_id']}/image",
            )
            for row in rows
        ]

    def count_alert_records(
        self,
        *,
        event_type: str | None = None,
        session_id: str | None = None,
        days: int | None = None,
    ) -> int:
        """Return total persisted alert count for the given filters."""
        filters: list[str] = []
        params: list[object] = []

        if event_type:
            filters.append("event_type = ?")
            params.append(event_type)
        if session_id:
            filters.append("session_id = ?")
            params.append(session_id)
        if days is not None:
            bounded_days = max(1, min(days, 30))
            cutoff = (
                datetime.now() - timedelta(days=bounded_days - 1)
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            filters.append("timestamp >= ?")
            params.append(cutoff.isoformat(timespec="seconds"))

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"SELECT COUNT(*) AS total FROM alert_records {where_sql}"

        with get_connection() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row["total"]) if row is not None else 0

    def list_session_options(self, limit: int = 20) -> list[SessionOptionPayload]:
        """Return recent detection sessions for records filtering."""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT session_id, started_at, video_source, status
                FROM detection_sessions
                ORDER BY COALESCE(started_at, '') DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            SessionOptionPayload(
                session_id=row["session_id"],
                started_at=row["started_at"],
                video_source=row["video_source"],
                status=row["status"],
            )
            for row in rows
        ]

    def count_detection_sessions(self) -> int:
        """Return total persisted detection session count."""
        with get_connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM detection_sessions"
            ).fetchone()
        return int(row["total"]) if row is not None else 0

    def count_unique_students(
        self,
        *,
        session_id: str | None = None,
        days: int = 7,
    ) -> int:
        """Return distinct student ID count from alert records in range."""
        where_sql, params = self._build_alert_filter_sql(
            session_id=session_id,
            days=days,
        )
        query = f"""
            SELECT COUNT(DISTINCT student_id) AS total
            FROM alert_records
            {where_sql}
        """
        with get_connection() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row["total"]) if row is not None else 0

    def get_event_breakdown(
        self,
        *,
        session_id: str | None = None,
        days: int = 7,
    ) -> list[AnalyticsEventItemPayload]:
        """Return event counts and rates for the selected range."""
        where_sql, params = self._build_alert_filter_sql(
            session_id=session_id,
            days=days,
        )
        query = f"""
            SELECT event_type, COUNT(*) AS total
            FROM alert_records
            {where_sql}
            GROUP BY event_type
            ORDER BY total DESC, event_type ASC
        """
        with get_connection() as connection:
            rows = connection.execute(query, params).fetchall()

        total = sum(int(row["total"]) for row in rows) or 1
        return [
            AnalyticsEventItemPayload(
                event_type=row["event_type"],
                label=self.EVENT_LABELS.get(row["event_type"], row["event_type"]),
                count=int(row["total"]),
                rate=round(int(row["total"]) / total, 4),
            )
            for row in rows
        ]

    def get_daily_alert_trend(
        self,
        *,
        session_id: str | None = None,
        days: int = 7,
    ) -> list[AnalyticsTrendPointPayload]:
        """Return daily alert counts over the recent range."""
        bounded_days = max(1, min(days, 30))
        start_date = datetime.now().date() - timedelta(days=bounded_days - 1)
        where_sql, params = self._build_alert_filter_sql(
            session_id=session_id,
            days=bounded_days,
        )
        query = f"""
            SELECT substr(timestamp, 1, 10) AS day_key, COUNT(*) AS total
            FROM alert_records
            {where_sql}
            GROUP BY day_key
            ORDER BY day_key ASC
        """
        with get_connection() as connection:
            rows = connection.execute(query, params).fetchall()

        counts_by_day = {str(row["day_key"]): int(row["total"]) for row in rows}
        return [
            AnalyticsTrendPointPayload(
                date=day.isoformat(),
                label=day.strftime("%m-%d"),
                count=counts_by_day.get(day.isoformat(), 0),
            )
            for day in (
                start_date + timedelta(days=offset) for offset in range(bounded_days)
            )
        ]

    def get_hourly_alert_distribution(
        self,
        *,
        session_id: str | None = None,
        days: int = 7,
    ) -> list[AnalyticsHourPointPayload]:
        """Return hourly alert distribution for the selected range."""
        where_sql, params = self._build_alert_filter_sql(
            session_id=session_id,
            days=days,
        )
        query = f"""
            SELECT substr(timestamp, 12, 2) AS hour_key, COUNT(*) AS total
            FROM alert_records
            {where_sql}
            GROUP BY hour_key
            ORDER BY hour_key ASC
        """
        with get_connection() as connection:
            rows = connection.execute(query, params).fetchall()

        counts_by_hour = {
            int(row["hour_key"]): int(row["total"])
            for row in rows
            if row["hour_key"] is not None
        }
        return [
            AnalyticsHourPointPayload(
                hour=hour,
                label=f"{hour:02d}:00",
                count=counts_by_hour.get(hour, 0),
            )
            for hour in range(24)
        ]

    def list_recent_session_analytics(
        self,
        limit: int = 6,
    ) -> list[AnalyticsSessionSummaryPayload]:
        """Return recent detection sessions with alert aggregates."""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    s.session_id,
                    s.started_at,
                    s.status,
                    s.video_source,
                    COUNT(a.alert_id) AS alert_count,
                    MAX(a.timestamp) AS last_alert_at
                FROM detection_sessions s
                LEFT JOIN alert_records a ON a.session_id = s.session_id
                GROUP BY s.session_id, s.started_at, s.status, s.video_source
                ORDER BY COALESCE(s.started_at, '') DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            top_event_rows = connection.execute(
                """
                SELECT
                    ranked.session_id,
                    ranked.event_type,
                    ranked.total
                FROM (
                    SELECT
                        session_id,
                        event_type,
                        COUNT(*) AS total,
                        ROW_NUMBER() OVER (
                            PARTITION BY session_id
                            ORDER BY COUNT(*) DESC, event_type ASC
                        ) AS ranking
                    FROM alert_records
                    GROUP BY session_id, event_type
                ) AS ranked
                WHERE ranked.ranking = 1
                """
            ).fetchall()

        top_event_map = {
            str(row["session_id"]): {
                "event_type": row["event_type"],
                "total": int(row["total"]),
            }
            for row in top_event_rows
        }

        return [
            AnalyticsSessionSummaryPayload(
                session_id=row["session_id"],
                started_at=row["started_at"],
                status=row["status"],
                video_source=row["video_source"],
                alert_count=int(row["alert_count"]),
                last_alert_at=row["last_alert_at"],
                top_event_type=top_event_map.get(row["session_id"], {}).get("event_type"),
                risk_score=min(100, int(row["alert_count"]) * 8),
            )
            for row in rows
        ]

    @staticmethod
    def _build_alert_filter_sql(
        *,
        session_id: str | None = None,
        days: int = 7,
    ) -> tuple[str, list[object]]:
        """Build a reusable WHERE clause for alert-record analytics queries."""
        filters: list[str] = []
        params: list[object] = []

        bounded_days = max(1, min(days, 30))
        cutoff = (
            datetime.now() - timedelta(days=bounded_days - 1)
        ).replace(hour=0, minute=0, second=0, microsecond=0)
        filters.append("timestamp >= ?")
        params.append(cutoff.isoformat(timespec="seconds"))

        if session_id:
            filters.append("session_id = ?")
            params.append(session_id)

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        return where_sql, params

    @staticmethod
    def resolve_snapshot_dir(raw_path: str) -> Path:
        """Resolve one configured snapshot directory into an absolute path."""
        normalized = raw_path.strip() or RuntimeStore.default_alert_snapshot_dir()
        path = Path(normalized)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path
