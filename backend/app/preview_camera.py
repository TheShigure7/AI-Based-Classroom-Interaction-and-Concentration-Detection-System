"""Run a minimal local camera preview window with YOLO classroom detection.

Dual-thread architecture:
- Main (display) thread: reads camera, draws latest results, shows frames at full FPS.
- Background (inference) thread: runs YOLO + MediaPipe + analysis on the newest frame,
  updates shared results for the display thread to consume.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import cv2
import numpy as np

from app.services.analysis.attention_analyzer import AttentionAnalyzer, AttentionSummary
from app.services.analysis.behavior_engine import BehaviorEngine
from app.services.camera.capture import CameraConfig, CameraService
from app.services.detection.yolo_detector import DetectionResult, YoloDetector
from app.services.pose.mediapipe_estimator import MediaPipePoseEstimator
from app.services.tracking.student_tracker import StudentTracker


# ---------------------------------------------------------------------------
# Shared state between display and inference threads
# ---------------------------------------------------------------------------


@dataclass
class SharedState:
    """Thread-safe shared state between display and inference threads."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    newest_frame: Optional[np.ndarray] = None
    frame_id: int = 0
    processed_frame_id: int = -1
    latest_detections: list[DetectionResult] = field(default_factory=list)
    latest_attention_summary: AttentionSummary = field(default_factory=AttentionSummary)
    running: bool = True

    # FPS counters
    display_fps: float = 0.0
    inference_fps: float = 0.0


# ---------------------------------------------------------------------------
# Helpers (unchanged logic, extracted from original main)
# ---------------------------------------------------------------------------


def _resolve_video_source() -> int | str:
    """Resolve local camera index or remote stream URL from environment."""
    raw_source = os.getenv("CLASSROOM_VIDEO_SOURCE", "0").strip()
    if raw_source.isdigit():
        return int(raw_source)
    parsed = urlparse(raw_source)
    if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path in {"", "/"}:
        return raw_source.rstrip("/") + "/video"
    return raw_source


def _bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    """Return bbox center."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _assign_display_ids(person_detections: list[DetectionResult]) -> None:
    """Assign display IDs from bottom-right to left, row by row."""
    sorted_detections = sorted(
        person_detections,
        key=lambda d: (_bbox_center(d.bbox)[1], _bbox_center(d.bbox)[0]),
        reverse=True,
    )
    for index, detection in enumerate(sorted_detections, start=1):
        detection.track_id = str(index)


# ---------------------------------------------------------------------------
# Inference thread
# ---------------------------------------------------------------------------


def inference_loop(
    state: SharedState,
    detector: YoloDetector,
    pose_estimator: MediaPipePoseEstimator,
    behavior_engine: BehaviorEngine,
    attention_analyzer: AttentionAnalyzer,
    student_tracker: StudentTracker,
) -> None:
    """Background thread: run heavy inference on the newest available frame."""

    tick_times: list[float] = []

    while True:
        # --- Check for exit signal & grab the newest frame ---
        has_frame = False
        with state.lock:
            if not state.running:
                break
            if state.frame_id > state.processed_frame_id:
                frame = state.newest_frame
                current_frame_id = state.frame_id
                has_frame = True

        if not has_frame:
            time.sleep(0.005)  # 5ms polling interval
            continue

        # Safety: frame should never be None here, but guard anyway
        if frame is None:
            with state.lock:
                state.processed_frame_id = current_frame_id
            continue

        t_start = time.perf_counter()

        # --- Heavy inference (no lock held — display thread runs freely) ---
        frame_copy = frame.copy()
        detections = detector.detect_targets(frame_copy)

        person_detections = [d for d in detections if d.label == "person"]
        phone_detections = [d for d in detections if d.label == "cell phone"]
        track_assignments = student_tracker.update([d.bbox for d in person_detections])
        pose_estimates: dict[int, object | None] = {}

        for index, detection in enumerate(person_detections):
            tracked_student = track_assignments[index]
            pose_estimate = pose_estimator.estimate_person_pose(frame_copy, detection.bbox)
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
            detection.attention_score = attention_analyzer.update_attention_score(tracked_student)

        _assign_display_ids(person_detections)
        attention_summary = attention_analyzer.summarize(list(track_assignments.values()))

        # --- Update shared results ---
        with state.lock:
            state.latest_detections = detections
            state.latest_attention_summary = attention_summary
            state.processed_frame_id = current_frame_id

        # --- Update inference FPS ---
        t_end = time.perf_counter()
        tick_times.append(t_end - t_start)
        if len(tick_times) > 30:
            tick_times.pop(0)
        avg_tick = sum(tick_times) / len(tick_times)
        if avg_tick > 0:
            with state.lock:
                state.inference_fps = 1.0 / avg_tick


# ---------------------------------------------------------------------------
# Main (display thread)
# ---------------------------------------------------------------------------


def main() -> None:
    stream_source = _resolve_video_source()
    camera = CameraService(config=CameraConfig(source=stream_source))
    detector = YoloDetector()
    pose_estimator = MediaPipePoseEstimator()
    attention_analyzer = AttentionAnalyzer()
    behavior_engine = BehaviorEngine(attention_analyzer=attention_analyzer)
    student_tracker = StudentTracker()

    state = SharedState()

    # Start background inference thread
    inference_thread = threading.Thread(
        target=inference_loop,
        args=(
            state,
            detector,
            pose_estimator,
            behavior_engine,
            attention_analyzer,
            student_tracker,
        ),
        daemon=True,
        name="inference",
    )
    inference_thread.start()

    camera.open()

    display_tick_times: list[float] = []

    try:
        while True:
            t_display_start = time.perf_counter()

            frame = camera.read_frame()

            # --- Copy latest results from inference thread ---
            with state.lock:
                detections = list(state.latest_detections)
                attention_summary = state.latest_attention_summary
                display_fps = state.display_fps
                inference_fps = state.inference_fps
                # Push frame to inference thread (always overwrite stale frame)
                state.newest_frame = frame
                state.frame_id += 1

            # --- Draw (fast — no inference here) ---
            output = detector.draw_detections(frame, detections)

            # Attention summary overlay
            cv2.putText(
                output,
                f"Attention avg: {attention_summary.average_score}",
                (20, 275),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                output,
                f"Low attention: {attention_summary.low_attention_count}",
                (20, 310),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 215, 255),
                2,
                cv2.LINE_AA,
            )

            # FPS overlay (top-right corner)
            h, w = output.shape[:2]
            fps_text = f"Display: {display_fps:.0f} FPS | Inference: {inference_fps:.1f} FPS"
            (tw, th), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.putText(
                output,
                fps_text,
                (w - tw - 15, th + 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("Classroom Camera + YOLO", output)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

            # --- Update display FPS ---
            t_display_end = time.perf_counter()
            display_tick_times.append(t_display_end - t_display_start)
            if len(display_tick_times) > 30:
                display_tick_times.pop(0)
            avg_display = sum(display_tick_times) / len(display_tick_times)
            if avg_display > 0:
                with state.lock:
                    state.display_fps = 1.0 / avg_display

    finally:
        state.running = False
        inference_thread.join(timeout=3.0)
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
