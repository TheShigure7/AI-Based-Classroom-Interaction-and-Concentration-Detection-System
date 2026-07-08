"""Service runtime for browser-based realtime classroom monitoring."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import cv2
import numpy as np

from app.models.schemas.analytics import AnalyticsOverviewResponse
from app.models.schemas.realtime import (
    AlertPayload,
    BBoxPayload,
    BehaviorCountsPayload,
    BehaviorRatesPayload,
    ClassroomCurrentResponse,
    PerformancePayload,
    RealtimeEvent,
    ResolutionPayload,
    SessionActionResponse,
    SessionPayload,
    StartSessionRequest,
    StudentPayload,
    StudentStatesPayload,
    SummaryPayload,
)
from app.models.schemas.records import RecordDeleteResponse, RecordsListResponse
from app.models.schemas.settings import SettingsPayload, UpdateSettingsRequest, VideoSourceOption
from app.services.analysis.attention_analyzer import AttentionAnalyzer, AttentionSummary
from app.services.analysis.behavior_engine import BehaviorEngine
from app.services.camera.capture import CameraConfig, CameraService
from app.services.detection.yolo_detector import DetectionResult, YoloDetector
from app.services.pose.mediapipe_estimator import MediaPipePoseEstimator
from app.services.storage import RuntimeStore
from app.services.storage.runtime_store import StoredAlertRecord
from app.services.tracking.student_tracker import StudentTracker


@dataclass
class AlertRecord:
    """Internal in-memory alert snapshot record."""

    alert_id: str
    timestamp: str
    student_id: str
    event_type: str
    attention_score: int
    snapshot_bytes: bytes
    snapshot_path: str = ""


@dataclass
class RuntimePipelineState:
    """Shared state between capture/render and inference threads."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    newest_frame: np.ndarray | None = None
    frame_id: int = 0
    processed_frame_id: int = -1
    latest_detections: list[DetectionResult] = field(default_factory=list)
    latest_attention_summary: AttentionSummary = field(default_factory=AttentionSummary)
    error_message: str = ""


class ClassroomRuntime:
    """Background runtime that powers the first-phase realtime web app."""

    LOW_ATTENTION_THRESHOLD = 60
    ALERT_EVENT_TYPES = (
        "hand_raised",
        "head_down",
        "phone_risk",
        "sleeping",
        "talking_risk",
        "low_attention",
    )
    ALERT_COOLDOWN_SECONDS = 5.0
    HAND_RAISE_ALERT_COOLDOWN_SECONDS = 10.0
    HEAD_DOWN_ALERT_COOLDOWN_SECONDS = 30.0
    PHONE_RISK_ALERT_COOLDOWN_SECONDS = 30.0
    SLEEPING_ALERT_COOLDOWN_SECONDS = 60.0
    ALERT_LIMIT = 24

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._store = RuntimeStore()

        self._status = "idle"
        self._session_id = ""
        self._video_source = "0"
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._enable_pose_analysis = True
        self._save_alert_snapshots = True
        self._last_error = ""

        self._resolution = ResolutionPayload(width=1280, height=720)
        self._performance = PerformancePayload()
        self._summary = SummaryPayload()
        self._students: list[StudentPayload] = []
        self._alerts: list[AlertRecord] = []
        self._alert_cooldowns: dict[tuple[str, str], float] = {}
        self._display_id_by_track: dict[str, str] = {}
        self._next_display_id = 1
        self._alert_sequence = 0
        self._latest_frame_jpeg: bytes | None = None
        self._latest_frame_version = 0
        default_settings = SettingsPayload(
            alert_snapshot_dir=self._store.default_alert_snapshot_dir(),
            recent_video_sources=[VideoSourceOption(label="本地摄像头", value="0")]
        )
        self._settings = self._store.load_settings(default_settings)

    def start_session(self, request: StartSessionRequest) -> SessionActionResponse:
        """Start a new runtime session if one is not already running."""
        with self._lock:
            if self._status == "running":
                return SessionActionResponse(
                    success=True,
                    message="session already running",
                    session=self._build_session_payload_locked(),
                )

            self._session_id = self._generate_session_id()
            self._video_source = request.video_source
            self._enable_pose_analysis = request.enable_pose_analysis
            self._save_alert_snapshots = request.save_alert_snapshots
            self._settings.enable_pose_analysis = request.enable_pose_analysis
            self._settings.save_alert_snapshots = request.save_alert_snapshots
            self._remember_video_source_locked(request.video_source)
            self._started_at = datetime.now()
            self._stopped_at = None
            self._status = "running"
            self._last_error = ""
            self._summary = SummaryPayload()
            self._students = []
            self._alerts = []
            self._alert_cooldowns = {}
            self._display_id_by_track = {}
            self._next_display_id = 1
            self._alert_sequence = 0
            self._latest_frame_jpeg = None
            self._latest_frame_version = 0
            self._performance = PerformancePayload()
            self._stop_event = threading.Event()

            self._thread = threading.Thread(
                target=self._run_session,
                daemon=True,
                name="classroom-runtime",
            )
            self._thread.start()
            response = SessionActionResponse(
                success=True,
                message="session started",
                session=self._build_session_payload_locked(),
            )
            self._persist_session_locked()
            return response

    def stop_session(self) -> SessionActionResponse:
        """Stop the current runtime session."""
        thread: threading.Thread | None = None
        with self._lock:
            if self._status != "running":
                self._status = "stopped" if self._session_id else "idle"
                self._stopped_at = datetime.now()
                return SessionActionResponse(
                    success=True,
                    message="session stopped",
                    session=self._build_session_payload_locked(),
                )

            self._stop_event.set()
            thread = self._thread

        if thread is not None:
            thread.join(timeout=5.0)

        with self._lock:
            if self._status == "running":
                self._status = "stopped"
            self._stopped_at = datetime.now()
            response = SessionActionResponse(
                success=True,
                message="session stopped",
                session=self._build_session_payload_locked(),
            )
            self._persist_session_locked()
            return response

    def get_session_status(self) -> SessionPayload:
        """Return the current session metadata."""
        with self._lock:
            return self._build_session_payload_locked()

    def get_current_state(self) -> ClassroomCurrentResponse:
        """Return the current classroom state for the realtime page."""
        with self._lock:
            return ClassroomCurrentResponse(
                running=self._status == "running",
                session_id=self._session_id,
                status=self._status,  # type: ignore[arg-type]
                video_source=self._video_source,
                duration_seconds=self._duration_seconds_locked(),
                last_error=self._last_error,
                resolution=self._resolution,
                performance=self._performance,
                summary=self._summary,
                students=list(self._students),
                latest_alerts=[self._serialize_alert(alert) for alert in self._alerts[:8]],
            )

    def get_settings(self) -> SettingsPayload:
        """Return lightweight frontend settings."""
        with self._lock:
            return self._settings.model_copy(deep=True)

    def update_settings(self, request: UpdateSettingsRequest) -> SettingsPayload:
        """Update lightweight frontend settings."""
        with self._lock:
            if request.local_camera_source is not None:
                self._settings.local_camera_source = request.local_camera_source
            if request.network_video_source is not None:
                self._settings.network_video_source = request.network_video_source
                if request.network_video_source.strip():
                    self._remember_video_source_locked(request.network_video_source)
            if request.enable_pose_analysis is not None:
                self._settings.enable_pose_analysis = request.enable_pose_analysis
            if request.enable_sleeping_detection is not None:
                self._settings.enable_sleeping_detection = request.enable_sleeping_detection
            if request.enable_talking_detection is not None:
                self._settings.enable_talking_detection = request.enable_talking_detection
            if request.low_attention_threshold is not None:
                self._settings.low_attention_threshold = request.low_attention_threshold
            if request.save_alert_snapshots is not None:
                self._settings.save_alert_snapshots = request.save_alert_snapshots
            if request.enable_realtime_alerts is not None:
                self._settings.enable_realtime_alerts = request.enable_realtime_alerts
            if request.enable_daily_summary is not None:
                self._settings.enable_daily_summary = request.enable_daily_summary
            if request.enable_email_summary is not None:
                self._settings.enable_email_summary = request.enable_email_summary
            if request.email_address is not None:
                self._settings.email_address = request.email_address
            if request.alert_snapshot_dir is not None:
                self._settings.alert_snapshot_dir = request.alert_snapshot_dir
            self._persist_settings_locked()
            return self._settings.model_copy(deep=True)

    def get_realtime_event(self) -> RealtimeEvent:
        """Return the current websocket event payload."""
        with self._lock:
            return RealtimeEvent(
                type="classroom_update",
                timestamp=self._now_iso(),
                session_id=self._session_id,
                status=self._status,  # type: ignore[arg-type]
                duration_seconds=self._duration_seconds_locked(),
                performance=self._performance,
                summary=self._summary,
                latest_alerts=[self._serialize_alert(alert) for alert in self._alerts[:8]],
            )

    def get_alert_snapshot(self, alert_id: str) -> bytes | None:
        """Return image bytes for one alert snapshot."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    return alert.snapshot_bytes
        snapshot_path = self._store.get_alert_snapshot_path(alert_id)
        if snapshot_path is None:
            return None
        path = Path(snapshot_path)
        if not path.exists():
            return None
        return path.read_bytes()

    def mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yield the latest video frame as an MJPEG stream."""
        last_version = -1
        while True:
            with self._lock:
                frame = self._latest_frame_jpeg
                frame_version = self._latest_frame_version
                running = self._status == "running"

            if frame is not None and frame_version != last_version:
                last_version = frame_version
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
                continue

            if frame is None and not running:
                blank = np.full((480, 854, 3), 235, dtype=np.uint8)
                cv2.putText(
                    blank,
                    "Classroom stream is not running",
                    (80, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (60, 60, 60),
                    2,
                    cv2.LINE_AA,
                )
                ok, encoded = cv2.imencode(".jpg", blank)
                if ok:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + encoded.tobytes()
                        + b"\r\n"
                    )

            time.sleep(0.01)

    def _run_session(self) -> None:
        """Background detection loop used by the first-phase web API."""
        capture_thread: threading.Thread | None = None
        inference_thread: threading.Thread | None = None
        camera: CameraService | None = None

        try:
            source = self._resolve_video_source(self._video_source)
            camera = CameraService(config=CameraConfig(source=source))
            detector = YoloDetector()
            pose_estimator = MediaPipePoseEstimator() if self._enable_pose_analysis else None
            attention_analyzer = AttentionAnalyzer()
            behavior_engine = BehaviorEngine(attention_analyzer=attention_analyzer)
            student_tracker = StudentTracker()
            pipeline = RuntimePipelineState()

            camera.open()

            capture_thread = threading.Thread(
                target=self._capture_render_loop,
                args=(pipeline, camera, detector),
                daemon=True,
                name="classroom-capture-render",
            )
            inference_thread = threading.Thread(
                target=self._inference_loop,
                args=(
                    pipeline,
                    detector,
                    pose_estimator,
                    behavior_engine,
                    attention_analyzer,
                    student_tracker,
                ),
                daemon=True,
                name="classroom-inference",
            )

            capture_thread.start()
            inference_thread.start()

            while not self._stop_event.is_set():
                with pipeline.lock:
                    if pipeline.error_message:
                        raise RuntimeError(pipeline.error_message)
                time.sleep(0.03)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._status = "error"
                self._last_error = str(exc)
                self._stopped_at = datetime.now()
                self._persist_session_locked()
        finally:
            self._stop_event.set()
            if capture_thread is not None:
                capture_thread.join(timeout=3.0)
            if inference_thread is not None:
                inference_thread.join(timeout=3.0)
            if camera is not None:
                camera.release()

            with self._lock:
                if self._status == "running":
                    self._status = "stopped"
                self._stopped_at = datetime.now()
                self._persist_session_locked()

    def _capture_render_loop(
        self,
        pipeline: RuntimePipelineState,
        camera: CameraService,
        detector: YoloDetector,
    ) -> None:
        """Continuously capture latest frames and render newest view for MJPEG output."""
        display_times: list[float] = []

        try:
            while not self._stop_event.is_set():
                display_start = time.perf_counter()
                frame = camera.read_frame()

                with pipeline.lock:
                    pipeline.newest_frame = frame
                    pipeline.frame_id += 1
                    detections = list(pipeline.latest_detections)
                    attention_summary = pipeline.latest_attention_summary

                output = detector.draw_detections(frame, detections)
                self._draw_runtime_overlays(output, attention_summary)
                ok, encoded = cv2.imencode(".jpg", output)
                frame_bytes = encoded.tobytes() if ok else None

                display_times = self._update_times(
                    display_times,
                    time.perf_counter() - display_start,
                )
                self._update_preview_frame(
                    frame=output,
                    frame_bytes=frame_bytes,
                    display_fps=self._fps_from_times(display_times),
                )
        except Exception as exc:  # noqa: BLE001
            with pipeline.lock:
                if not pipeline.error_message:
                    pipeline.error_message = str(exc)
            self._stop_event.set()

    def _inference_loop(
        self,
        pipeline: RuntimePipelineState,
        detector: YoloDetector,
        pose_estimator: MediaPipePoseEstimator | None,
        behavior_engine: BehaviorEngine,
        attention_analyzer: AttentionAnalyzer,
        student_tracker: StudentTracker,
    ) -> None:
        """Run heavy inference only on the newest available frame and drop stale ones."""
        inference_times: list[float] = []

        try:
            while not self._stop_event.is_set():
                has_frame = False
                frame: np.ndarray | None = None
                current_frame_id = -1

                with pipeline.lock:
                    if pipeline.frame_id > pipeline.processed_frame_id:
                        frame = pipeline.newest_frame
                        current_frame_id = pipeline.frame_id
                        has_frame = True

                if not has_frame:
                    time.sleep(0.005)
                    continue

                if frame is None:
                    with pipeline.lock:
                        pipeline.processed_frame_id = current_frame_id
                    continue

                inference_start = time.perf_counter()
                frame_copy = frame.copy()
                detections = detector.detect_targets(frame_copy)

                person_detections = [d for d in detections if d.label == "person"]
                phone_detections = [d for d in detections if d.label == "cell phone"]
                track_assignments = student_tracker.update([d.bbox for d in person_detections])
                pose_estimates: dict[int, Any | None] = {}

                for index, detection in enumerate(person_detections):
                    tracked_student = track_assignments[index]
                    pose_estimate = (
                        pose_estimator.estimate_person_pose(frame_copy, detection.bbox)
                        if pose_estimator is not None
                        else None
                    )
                    pose_estimates[index] = pose_estimate
                    behavior_state = behavior_engine.analyze_person(
                        detection,
                        tracked_student,
                        phone_detections,
                        pose_estimate,
                    )
                    behavior_engine.apply_behavior_state(
                        detection,
                        tracked_student,
                        behavior_state,
                    )

                talking_track_ids = behavior_engine.analyze_scene_talking(
                    person_detections,
                    track_assignments,
                    pose_estimates,
                )
                behavior_engine.apply_talking_states(
                    person_detections,
                    track_assignments,
                    talking_track_ids,
                )

                for index, detection in enumerate(person_detections):
                    tracked_student = track_assignments[index]
                    detection.attention_score = attention_analyzer.update_attention_score(
                        tracked_student
                    )

                self._assign_display_ids(person_detections)
                attention_summary = attention_analyzer.summarize(list(track_assignments.values()))

                with pipeline.lock:
                    pipeline.latest_detections = detections
                    pipeline.latest_attention_summary = attention_summary
                    pipeline.processed_frame_id = current_frame_id

                inference_times = self._update_times(
                    inference_times,
                    time.perf_counter() - inference_start,
                )
                self._update_inference_state(
                    frame=frame_copy,
                    person_detections=person_detections,
                    attention_summary=attention_summary,
                    inference_fps=self._fps_from_times(inference_times),
                )
        except Exception as exc:  # noqa: BLE001
            with pipeline.lock:
                if not pipeline.error_message:
                    pipeline.error_message = str(exc)
            self._stop_event.set()

    def _update_preview_frame(
        self,
        frame: np.ndarray,
        frame_bytes: bytes | None,
        display_fps: float,
    ) -> None:
        """Publish the newest rendered frame for MJPEG output."""
        with self._lock:
            self._resolution = ResolutionPayload(
                width=int(frame.shape[1]),
                height=int(frame.shape[0]),
            )
            self._performance = PerformancePayload(
                inference_fps=self._performance.inference_fps,
                display_fps=round(display_fps, 1),
            )
            if frame_bytes is not None:
                self._latest_frame_jpeg = frame_bytes
                self._latest_frame_version += 1

    def _update_inference_state(
        self,
        frame: np.ndarray,
        person_detections: list[DetectionResult],
        attention_summary: AttentionSummary,
        inference_fps: float,
    ) -> None:
        """Update summary, students, alerts, and inference FPS from processed detections."""
        students = [self._serialize_student(detection) for detection in person_detections]
        student_count = len(person_detections)
        behavior_counts = BehaviorCountsPayload(
            hand_raised=sum(1 for d in person_detections if d.hand_raised),
            head_down=sum(1 for d in person_detections if d.head_down),
            phone_risk=sum(1 for d in person_detections if d.phone_risk),
            sleeping=sum(1 for d in person_detections if d.sleeping),
            talking_risk=sum(1 for d in person_detections if d.talking_risk),
        )
        behavior_rates = BehaviorRatesPayload(
            **{
                field: round((getattr(behavior_counts, field) / student_count), 2)
                if student_count
                else 0.0
                for field in behavior_counts.model_fields
            }
        )

        with self._lock:
            self._performance = PerformancePayload(
                inference_fps=round(inference_fps, 1),
                display_fps=self._performance.display_fps,
            )
            self._summary = SummaryPayload(
                student_count=student_count,
                average_attention=attention_summary.average_score,
                low_attention_count=attention_summary.low_attention_count,
                behavior_counts=behavior_counts,
                behavior_rates=behavior_rates,
            )
            self._students = students
            self._refresh_alerts_locked(frame, person_detections)

    def _refresh_alerts_locked(
        self,
        frame: np.ndarray,
        person_detections: list[DetectionResult],
    ) -> None:
        """Refresh in-memory alert list from the latest frame."""
        if not self._save_alert_snapshots:
            return

        now = time.time()
        for detection in person_detections:
            event_types = self._pick_alert_event_types(detection)
            if not event_types:
                continue

            snapshot_bytes = self._encode_snapshot(frame, detection.bbox)
            if snapshot_bytes is None:
                continue

            for event_type in event_types:
                key = (detection.track_id or "unknown", event_type)
                last_time = self._alert_cooldowns.get(key, 0.0)
                if now - last_time < self._cooldown_for_event_type(event_type):
                    continue

                self._alert_sequence += 1
                alert_id = f"{self._session_id}_{self._alert_sequence:04d}"
                timestamp = self._now_iso()
                snapshot_path = self._write_alert_snapshot(
                    alert_id=alert_id,
                    timestamp=timestamp,
                    snapshot_bytes=snapshot_bytes,
                )
                alert = AlertRecord(
                    alert_id=alert_id,
                    timestamp=timestamp,
                    student_id=detection.display_id or detection.track_id or "unknown",
                    event_type=event_type,
                    attention_score=int(detection.attention_score),
                    snapshot_bytes=snapshot_bytes,
                    snapshot_path=str(snapshot_path),
                )
                self._alerts.insert(0, alert)
                self._alerts = self._alerts[: self.ALERT_LIMIT]
                self._alert_cooldowns[key] = now
                self._store.save_alert_record(
                    StoredAlertRecord(
                        alert_id=alert.alert_id,
                        session_id=self._session_id,
                        timestamp=alert.timestamp,
                        student_id=alert.student_id,
                        event_type=alert.event_type,
                        attention_score=alert.attention_score,
                        snapshot_path=alert.snapshot_path,
                    )
                )

    def list_records(
        self,
        *,
        event_type: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> RecordsListResponse:
        """Return persisted alert records for the records page."""
        items = self._store.list_alert_records(
            event_type=event_type,
            session_id=session_id,
            limit=limit,
        )
        total = self._store.count_alert_records(
            event_type=event_type,
            session_id=session_id,
        )
        sessions = self._store.list_session_options()
        return RecordsListResponse(
            total=total,
            items=items,
            sessions=sessions,
        )

    def delete_record(self, alert_id: str) -> RecordDeleteResponse:
        """Delete one persisted record and its saved snapshot file."""
        snapshot_path = self._store.delete_alert_record(alert_id)
        if snapshot_path is None:
            return RecordDeleteResponse(success=False, alert_id=alert_id)

        with self._lock:
            self._alerts = [alert for alert in self._alerts if alert.alert_id != alert_id]

        path = Path(snapshot_path)
        if path.exists():
            path.unlink(missing_ok=True)

        return RecordDeleteResponse(success=True, alert_id=alert_id)

    def get_analytics_overview(
        self,
        *,
        session_id: str | None = None,
        days: int = 7,
    ) -> AnalyticsOverviewResponse:
        """Return persisted analytics plus the latest in-memory classroom summary."""
        bounded_days = max(1, min(days, 30))
        with self._lock:
            current_summary = self._summary.model_copy(deep=True)

        return AnalyticsOverviewResponse(
            generated_at=self._now_iso(),
            days=bounded_days,
            selected_session_id=session_id,
            current_summary=current_summary,
            total_sessions=self._store.count_detection_sessions(),
            total_alerts=self._store.count_alert_records(
                session_id=session_id,
                days=bounded_days,
            ),
            unique_students=self._store.count_unique_students(
                session_id=session_id,
                days=bounded_days,
            ),
            event_breakdown=self._store.get_event_breakdown(
                session_id=session_id,
                days=bounded_days,
            ),
            daily_trend=self._store.get_daily_alert_trend(
                session_id=session_id,
                days=bounded_days,
            ),
            hourly_distribution=self._store.get_hourly_alert_distribution(
                session_id=session_id,
                days=bounded_days,
            ),
            recent_sessions=self._store.list_recent_session_analytics(),
            sessions=self._store.list_session_options(),
        )

    def _build_session_payload_locked(self) -> SessionPayload:
        return SessionPayload(
            session_id=self._session_id,
            status=self._status,  # type: ignore[arg-type]
            video_source=self._video_source,
            started_at=self._started_at.isoformat(timespec="seconds")
            if self._started_at is not None
            else None,
            stopped_at=self._stopped_at.isoformat(timespec="seconds")
            if self._stopped_at is not None
            else None,
            duration_seconds=self._duration_seconds_locked(),
            enable_pose_analysis=self._enable_pose_analysis,
            save_alert_snapshots=self._save_alert_snapshots,
            last_error=self._last_error,
        )

    def _duration_seconds_locked(self) -> int:
        if self._started_at is None:
            return 0
        end_time = (
            datetime.now()
            if self._status == "running"
            else (self._stopped_at or datetime.now())
        )
        return max(0, int((end_time - self._started_at).total_seconds()))

    @staticmethod
    def _serialize_student(detection: DetectionResult) -> StudentPayload:
        return StudentPayload(
            student_id=detection.display_id or detection.track_id or "unknown",
            track_id=detection.track_id or "unknown",
            bbox=BBoxPayload(
                x1=detection.bbox[0],
                y1=detection.bbox[1],
                x2=detection.bbox[2],
                y2=detection.bbox[3],
            ),
            attention_score=int(detection.attention_score),
            is_low_attention=int(detection.attention_score)
            < ClassroomRuntime.LOW_ATTENTION_THRESHOLD,
            states=StudentStatesPayload(
                hand_raised=detection.hand_raised,
                head_down=detection.head_down,
                phone_risk=detection.phone_risk,
                sleeping=detection.sleeping,
                talking_risk=detection.talking_risk,
            ),
        )

    @staticmethod
    def _serialize_alert(alert: AlertRecord) -> AlertPayload:
        return AlertPayload(
            alert_id=alert.alert_id,
            timestamp=alert.timestamp,
            student_id=alert.student_id,
            event_type=alert.event_type,  # type: ignore[arg-type]
            attention_score=alert.attention_score,
            snapshot_url=f"/api/v1/alerts/{alert.alert_id}/image",
        )

    @staticmethod
    def _encode_snapshot(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> bytes | None:
        x1, y1, x2, y2 = bbox
        pad = 30
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(frame.shape[1], x2 + pad)
        y2 = min(frame.shape[0], y2 + pad)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        ok, encoded = cv2.imencode(".jpg", crop)
        return encoded.tobytes() if ok else None

    @staticmethod
    def _pick_alert_event_types(detection: DetectionResult) -> list[str]:
        event_types: list[str] = []
        if detection.sleeping:
            event_types.append("sleeping")
        if detection.phone_risk:
            event_types.append("phone_risk")
        if detection.talking_risk:
            event_types.append("talking_risk")
        if detection.head_down:
            event_types.append("head_down")
        if detection.hand_raised:
            event_types.append("hand_raised")
        if (
            int(detection.attention_score) < ClassroomRuntime.LOW_ATTENTION_THRESHOLD
            and not {"sleeping", "phone_risk", "talking_risk", "head_down"} & set(event_types)
        ):
            event_types.append("low_attention")
        return event_types

    @staticmethod
    def _update_times(times: list[float], value: float) -> list[float]:
        times.append(value)
        if len(times) > 30:
            times.pop(0)
        return times

    @staticmethod
    def _fps_from_times(times: list[float]) -> float:
        if not times:
            return 0.0
        avg_time = sum(times) / len(times)
        return 1.0 / avg_time if avg_time > 0 else 0.0

    @staticmethod
    def _draw_runtime_overlays(frame: np.ndarray, attention_summary: AttentionSummary) -> None:
        cv2.putText(
            frame,
            f"Attention avg: {attention_summary.average_score}",
            (20, 275),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"Low attention: {attention_summary.low_attention_count}",
            (20, 310),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 215, 255),
            2,
            cv2.LINE_AA,
        )

    @staticmethod
    def _bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _assign_display_ids(self, person_detections: list[DetectionResult]) -> None:
        for detection in person_detections:
            if not detection.track_id:
                detection.display_id = "unknown"
                continue

            display_id = self._display_id_by_track.get(detection.track_id)
            if display_id is None:
                display_id = str(self._next_display_id)
                self._display_id_by_track[detection.track_id] = display_id
                self._next_display_id += 1
            detection.display_id = display_id

    @classmethod
    def _cooldown_for_event_type(cls, event_type: str) -> float:
        if event_type == "hand_raised":
            return cls.HAND_RAISE_ALERT_COOLDOWN_SECONDS
        if event_type == "head_down":
            return cls.HEAD_DOWN_ALERT_COOLDOWN_SECONDS
        if event_type == "phone_risk":
            return cls.PHONE_RISK_ALERT_COOLDOWN_SECONDS
        if event_type == "sleeping":
            return cls.SLEEPING_ALERT_COOLDOWN_SECONDS
        return cls.ALERT_COOLDOWN_SECONDS

    @staticmethod
    def _resolve_video_source(raw_source: str) -> int | str:
        raw_source = raw_source.strip()
        if raw_source.isdigit():
            return int(raw_source)
        parsed = urlparse(raw_source)
        if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path in {"", "/"}:
            return raw_source.rstrip("/") + "/video"
        return raw_source

    @staticmethod
    def _generate_session_id() -> str:
        return datetime.now().strftime("SESSION_%Y%m%d_%H%M%S")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _remember_video_source_locked(self, source: str) -> None:
        normalized_source = source.strip()
        if not normalized_source:
            return

        existing = [
            option
            for option in self._settings.recent_video_sources
            if option.value != normalized_source
        ]
        label = "本地摄像头" if normalized_source == "0" else normalized_source
        existing.insert(0, VideoSourceOption(label=label, value=normalized_source))
        self._settings.recent_video_sources = existing[:8]
        self._store.remember_video_source(
            value=normalized_source,
            label=label,
            used_at=self._now_iso(),
        )
        self._persist_settings_locked()

    def _persist_settings_locked(self) -> None:
        """Persist current settings to local storage."""
        self._store.save_settings(self._settings)

    def _persist_session_locked(self) -> None:
        """Persist current session metadata to local storage."""
        if not self._session_id:
            return
        self._store.upsert_session(
            session_id=self._session_id,
            video_source=self._video_source,
            started_at=(
                self._started_at.isoformat(timespec="seconds")
                if self._started_at is not None
                else None
            ),
            stopped_at=(
                self._stopped_at.isoformat(timespec="seconds")
                if self._stopped_at is not None
                else None
            ),
            status=self._status,
            enable_pose_analysis=self._enable_pose_analysis,
            save_alert_snapshots=self._save_alert_snapshots,
            last_error=self._last_error,
        )

    def _write_alert_snapshot(
        self,
        alert_id: str,
        timestamp: str,
        snapshot_bytes: bytes,
    ) -> Path:
        """Write one alert snapshot to the configured directory."""
        snapshot_dir = self._store.resolve_snapshot_dir(self._settings.alert_snapshot_dir)
        date_part = timestamp[:10]
        target_dir = snapshot_dir / date_part / (self._session_id or "session_unknown")
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{alert_id}.jpg"
        target_path.write_bytes(snapshot_bytes)
        return target_path
