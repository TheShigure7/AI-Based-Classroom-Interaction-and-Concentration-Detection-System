"""Service runtime for browser-based realtime classroom monitoring."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import cv2
import numpy as np

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
from app.services.analysis.attention_analyzer import AttentionAnalyzer
from app.services.analysis.behavior_engine import BehaviorEngine
from app.services.camera.capture import CameraConfig, CameraService
from app.services.detection.yolo_detector import DetectionResult, YoloDetector
from app.services.pose.mediapipe_estimator import MediaPipePoseEstimator
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


class ClassroomRuntime:
    """Background runtime that powers the first-phase realtime web app."""

    LOW_ATTENTION_THRESHOLD = 60
    ALERT_EVENT_TYPES = ("phone_risk", "sleeping", "talking_risk", "low_attention")
    ALERT_COOLDOWN_SECONDS = 5.0
    ALERT_LIMIT = 24

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

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
        self._latest_frame_jpeg: bytes | None = None

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
            self._started_at = datetime.now()
            self._stopped_at = None
            self._status = "running"
            self._last_error = ""
            self._summary = SummaryPayload()
            self._students = []
            self._alerts = []
            self._alert_cooldowns = {}
            self._latest_frame_jpeg = None
            self._performance = PerformancePayload()
            self._stop_event = threading.Event()

            self._thread = threading.Thread(
                target=self._run_session,
                daemon=True,
                name="classroom-runtime",
            )
            self._thread.start()

            return SessionActionResponse(
                success=True,
                message="session started",
                session=self._build_session_payload_locked(),
            )

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
            return SessionActionResponse(
                success=True,
                message="session stopped",
                session=self._build_session_payload_locked(),
            )

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
                resolution=self._resolution,
                performance=self._performance,
                summary=self._summary,
                students=list(self._students),
                latest_alerts=[self._serialize_alert(alert) for alert in self._alerts[:8]],
            )

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
        return None

    def mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yield the latest video frame as an MJPEG stream."""
        while True:
            with self._lock:
                frame = self._latest_frame_jpeg
                running = self._status == "running"

            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            elif not running:
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

            time.sleep(0.08)

    def _run_session(self) -> None:
        """Background detection loop used by the first-phase web API."""
        try:
            source = self._resolve_video_source(self._video_source)
            camera = CameraService(config=CameraConfig(source=source))
            detector = YoloDetector()
            pose_estimator = MediaPipePoseEstimator() if self._enable_pose_analysis else None
            attention_analyzer = AttentionAnalyzer()
            behavior_engine = BehaviorEngine(attention_analyzer=attention_analyzer)
            student_tracker = StudentTracker()

            camera.open()
            inference_times: list[float] = []
            display_times: list[float] = []

            while not self._stop_event.is_set():
                loop_start = time.perf_counter()
                frame = camera.read_frame()
                detections = detector.detect_targets(frame)
                person_detections = [d for d in detections if d.label == "person"]
                phone_detections = [d for d in detections if d.label == "cell phone"]
                track_assignments = student_tracker.update([d.bbox for d in person_detections])
                pose_estimates: dict[int, Any | None] = {}

                t_inference_start = time.perf_counter()
                for index, detection in enumerate(person_detections):
                    tracked_student = track_assignments[index]
                    pose_estimate = (
                        pose_estimator.estimate_person_pose(frame, detection.bbox)
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
                inference_times = self._update_times(
                    inference_times,
                    time.perf_counter() - t_inference_start,
                )

                output = detector.draw_detections(frame, detections)
                self._draw_runtime_overlays(output, attention_summary)
                ok, encoded = cv2.imencode(".jpg", output)
                if ok:
                    frame_bytes = encoded.tobytes()
                else:
                    frame_bytes = None

                display_times = self._update_times(
                    display_times,
                    time.perf_counter() - loop_start,
                )

                self._update_runtime_state(
                    frame=output,
                    frame_bytes=frame_bytes,
                    person_detections=person_detections,
                    attention_summary=attention_summary,
                    inference_fps=self._fps_from_times(inference_times),
                    display_fps=self._fps_from_times(display_times),
                )

            camera.release()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._status = "error"
                self._last_error = str(exc)
                self._stopped_at = datetime.now()
        finally:
            with self._lock:
                if self._status == "running":
                    self._status = "stopped"
                self._stopped_at = datetime.now()

    def _update_runtime_state(
        self,
        frame: np.ndarray,
        frame_bytes: bytes | None,
        person_detections: list[DetectionResult],
        attention_summary: Any,
        inference_fps: float,
        display_fps: float,
    ) -> None:
        """Update shared runtime state from the latest processed frame."""
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
            self._resolution = ResolutionPayload(
                width=int(frame.shape[1]),
                height=int(frame.shape[0]),
            )
            self._performance = PerformancePayload(
                inference_fps=round(inference_fps, 1),
                display_fps=round(display_fps, 1),
            )
            self._summary = SummaryPayload(
                student_count=student_count,
                average_attention=attention_summary.average_score,
                low_attention_count=attention_summary.low_attention_count,
                behavior_counts=behavior_counts,
                behavior_rates=behavior_rates,
            )
            self._students = students
            if frame_bytes is not None:
                self._latest_frame_jpeg = frame_bytes
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
            event_type = self._pick_alert_event_type(detection)
            if event_type is None:
                continue

            key = (detection.track_id or detection.track_id or "unknown", event_type)
            last_time = self._alert_cooldowns.get(key, 0.0)
            if now - last_time < self.ALERT_COOLDOWN_SECONDS:
                continue

            snapshot_bytes = self._encode_snapshot(frame, detection.bbox)
            if snapshot_bytes is None:
                continue

            alert = AlertRecord(
                alert_id=f"ALERT_{len(self._alerts) + 1:04d}",
                timestamp=self._now_iso(),
                student_id=detection.track_id or "unknown",
                event_type=event_type,
                attention_score=int(detection.attention_score),
                snapshot_bytes=snapshot_bytes,
            )
            self._alerts.insert(0, alert)
            self._alerts = self._alerts[: self.ALERT_LIMIT]
            self._alert_cooldowns[key] = now

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
        )

    def _duration_seconds_locked(self) -> int:
        if self._started_at is None:
            return 0
        end_time = datetime.now() if self._status == "running" else (self._stopped_at or datetime.now())
        return max(0, int((end_time - self._started_at).total_seconds()))

    @staticmethod
    def _serialize_student(detection: DetectionResult) -> StudentPayload:
        return StudentPayload(
            student_id=detection.track_id or "unknown",
            track_id=detection.track_id or "unknown",
            bbox=BBoxPayload(
                x1=detection.bbox[0],
                y1=detection.bbox[1],
                x2=detection.bbox[2],
                y2=detection.bbox[3],
            ),
            attention_score=int(detection.attention_score),
            is_low_attention=int(detection.attention_score) < ClassroomRuntime.LOW_ATTENTION_THRESHOLD,
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
    def _pick_alert_event_type(detection: DetectionResult) -> str | None:
        if detection.sleeping:
            return "sleeping"
        if detection.phone_risk:
            return "phone_risk"
        if detection.talking_risk:
            return "talking_risk"
        if int(detection.attention_score) < ClassroomRuntime.LOW_ATTENTION_THRESHOLD:
            return "low_attention"
        return None

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
    def _draw_runtime_overlays(frame: np.ndarray, attention_summary: Any) -> None:
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

    @classmethod
    def _assign_display_ids(cls, person_detections: list[DetectionResult]) -> None:
        sorted_detections = sorted(
            person_detections,
            key=lambda d: (cls._bbox_center(d.bbox)[1], cls._bbox_center(d.bbox)[0]),
            reverse=True,
        )
        for index, detection in enumerate(sorted_detections, start=1):
            detection.track_id = str(index)

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
