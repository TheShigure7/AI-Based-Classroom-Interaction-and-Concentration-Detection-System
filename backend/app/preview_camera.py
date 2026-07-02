"""Run a minimal local camera preview window with YOLO classroom detection."""

from __future__ import annotations

import cv2
import os
from urllib.parse import urlparse

from app.services.analysis.attention_analyzer import AttentionAnalyzer
from app.services.analysis.hand_raise_analyzer import HandRaiseAnalyzer
from app.services.analysis.phone_use_analyzer import PhoneUseAnalyzer
from app.services.camera.capture import CameraConfig, CameraService
from app.services.detection.yolo_detector import YoloDetector
from app.services.pose.mediapipe_estimator import MediaPipePoseEstimator
from app.services.tracking.student_tracker import StudentTracker


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


def _assign_display_ids(person_detections) -> None:
    """Assign display IDs from bottom-right to left, row by row."""
    sorted_detections = sorted(
        person_detections,
        key=lambda detection: (_bbox_center(detection.bbox)[1], _bbox_center(detection.bbox)[0]),
        reverse=True,
    )
    for index, detection in enumerate(sorted_detections, start=1):
        detection.track_id = str(index)


def main() -> None:
    stream_source = _resolve_video_source()
    camera = CameraService(config=CameraConfig(source=stream_source))
    detector = YoloDetector()
    pose_estimator = MediaPipePoseEstimator()
    hand_raise_analyzer = HandRaiseAnalyzer()
    attention_analyzer = AttentionAnalyzer()
    phone_use_analyzer = PhoneUseAnalyzer()
    student_tracker = StudentTracker()

    camera.open()
    try:
        while True:
            frame = camera.read_frame()
            detections = detector.detect_targets(frame)
            person_detections = [d for d in detections if d.label == "person"]
            phone_detections = [d for d in detections if d.label == "cell phone"]
            track_assignments = student_tracker.update([d.bbox for d in person_detections])

            for index, detection in enumerate(person_detections):
                tracked_student = track_assignments[index]
                detection.attention_score = round(tracked_student.attention_score)

                pose_estimate = pose_estimator.estimate_person_pose(frame, detection.bbox)
                if pose_estimate is None:
                    tracked_student.hand_raised = False
                    tracked_student.head_down = False
                    tracked_student.phone_risk = False
                    detection.attention_score = attention_analyzer.update_attention_score(tracked_student)
                    continue

                detection.hand_raised = hand_raise_analyzer.analyze(
                    pose_estimate.landmarks
                )
                detection.head_down = attention_analyzer.is_head_down(
                    pose_estimate.landmarks
                )
                detection.phone_risk = any(
                    phone_use_analyzer.is_phone_risk(
                        detection.bbox,
                        phone_detection.bbox,
                        detection.head_down,
                    )
                    for phone_detection in phone_detections
                )
                tracked_student.hand_raised = detection.hand_raised
                tracked_student.head_down = detection.head_down
                tracked_student.phone_risk = detection.phone_risk
                detection.attention_score = attention_analyzer.update_attention_score(tracked_student)

            _assign_display_ids(person_detections)
            attention_summary = attention_analyzer.summarize(list(track_assignments.values()))
            output = detector.draw_detections(frame, detections)
            cv2.putText(
                output,
                f"Attention avg: {attention_summary.average_score}",
                (20, 205),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                output,
                f"Low attention: {attention_summary.low_attention_count}",
                (20, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 215, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("Classroom Camera + YOLO", output)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
