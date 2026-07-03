"""Minimal YOLO detection service for classroom MVP."""

from __future__ import annotations

from dataclasses import dataclass
import cv2
import numpy as np
from ultralytics import YOLO


@dataclass
class DetectionResult:
    """Normalized detection output for downstream drawing and analysis."""

    label: str
    confidence: float
    bbox: tuple[int, int, int, int]
    track_id: str = ""
    attention_score: int = 100
    hand_raised: bool = False
    head_down: bool = False
    phone_risk: bool = False
    sleeping: bool = False
    talking_risk: bool = False


class YoloDetector:
    """Wraps an Ultralytics detection model."""

    TARGET_LABELS = {"person", "cell phone"}
    LABEL_STYLES = {
        "person": {"color": (0, 200, 0), "display": "student"},
        "cell phone": {"color": (0, 120, 255), "display": "phone"},
    }
    LOW_ATTENTION_THRESHOLD = 60

    def __init__(
        self,
        model_name: str = "yolo11n.pt",
        conf_threshold: float = 0.35,
    ) -> None:
        self.model_name = model_name
        self.conf_threshold = conf_threshold
        self.model = YOLO(model_name)

    def detect_targets(self, frame: np.ndarray) -> list[DetectionResult]:
        """Return supported classroom detections from a frame."""
        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            verbose=False,
        )

        detections: list[DetectionResult] = []
        for result in results:
            names = result.names
            boxes = result.boxes
            if boxes is None:
                continue

            for box in boxes:
                cls_id = int(box.cls.item())
                label = names.get(cls_id, str(cls_id))
                if label not in self.TARGET_LABELS:
                    continue

                confidence = float(box.conf.item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    DetectionResult(
                        label=label,
                        confidence=confidence,
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                    )
                )

        return detections

    def count_by_label(
        self,
        detections: list[DetectionResult],
    ) -> dict[str, int]:
        """Count detections by label."""
        counts = {label: 0 for label in self.TARGET_LABELS}
        for detection in detections:
            counts[detection.label] = counts.get(detection.label, 0) + 1
        return counts

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: list[DetectionResult],
    ) -> np.ndarray:
        """Draw person and phone detections on a frame."""
        output = frame.copy()
        counts = self.count_by_label(detections)

        for detection in detections:
            x1, y1, x2, y2 = detection.bbox
            style = self.LABEL_STYLES.get(
                detection.label,
                {"color": (255, 255, 255), "display": detection.label},
            )
            color = (
                self._resolve_person_color(detection)
                if detection.label == "person"
                else style["color"]
            )
            display_name = style["display"]

            cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                output,
                self._build_primary_label(detection, display_name),
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )
            if detection.label == "person":
                self._draw_person_statuses(output, detection)

        cv2.putText(
            output,
            f"Students: {counts.get('person', 0)}",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            output,
            f"Phones: {counts.get('cell phone', 0)}",
            (20, 65),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 165, 255),
            2,
            cv2.LINE_AA,
        )
        raised_count = sum(
            1 for detection in detections if detection.label == "person" and detection.hand_raised
        )
        cv2.putText(
            output,
            f"Hands raised: {raised_count}",
            (20, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )
        head_down_count = sum(
            1 for detection in detections if detection.label == "person" and detection.head_down
        )
        cv2.putText(
            output,
            f"Heads down: {head_down_count}",
            (20, 135),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        phone_risk_count = sum(
            1 for detection in detections if detection.label == "person" and detection.phone_risk
        )
        cv2.putText(
            output,
            f"Phone risk: {phone_risk_count}",
            (20, 170),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 140, 255),
            2,
            cv2.LINE_AA,
        )
        sleeping_count = sum(
            1 for detection in detections if detection.label == "person" and detection.sleeping
        )
        cv2.putText(
            output,
            f"Sleep risk: {sleeping_count}",
            (20, 205),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (180, 105, 255),
            2,
            cv2.LINE_AA,
        )
        talking_count = sum(
            1 for detection in detections if detection.label == "person" and detection.talking_risk
        )
        cv2.putText(
            output,
            f"Talking risk: {talking_count}",
            (20, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 128, 255),
            2,
            cv2.LINE_AA,
        )
        return output

    @staticmethod
    def _build_primary_label(detection: DetectionResult, display_name: str) -> str:
        """Build the top label shown above the bbox."""
        if detection.label == "person" and detection.track_id:
            label = f"{detection.track_id} | {detection.attention_score}"
            if detection.attention_score < YoloDetector.LOW_ATTENTION_THRESHOLD:
                label += " LOW"
            return label
        return f"{display_name} {detection.confidence:.2f}"

    @staticmethod
    def _resolve_person_color(detection: DetectionResult) -> tuple[int, int, int]:
        """Resolve bbox color from current student state."""
        if detection.phone_risk:
            return (0, 0, 255)
        if detection.sleeping:
            return (180, 105, 255)
        if detection.talking_risk:
            return (0, 128, 255)
        if detection.head_down:
            return (0, 255, 255)
        if detection.hand_raised:
            return (255, 0, 0)
        return (0, 200, 0)

    @staticmethod
    def _draw_person_statuses(output: np.ndarray, detection: DetectionResult) -> None:
        """Draw stacked status labels below one student bbox."""
        statuses: list[tuple[str, tuple[int, int, int]]] = []
        if detection.hand_raised:
            statuses.append(("hand raised", (255, 255, 0)))
        if detection.head_down:
            statuses.append(("head down", (0, 0, 255)))
        if detection.phone_risk:
            statuses.append(("phone risk", (0, 140, 255)))
        if detection.sleeping:
            statuses.append(("sleep risk", (180, 105, 255)))
        if detection.talking_risk:
            statuses.append(("talking risk", (0, 128, 255)))

        x1, _, _, y2 = detection.bbox
        for index, (label, color) in enumerate(statuses, start=1):
            cv2.putText(
                output,
                label,
                (x1, min(y2 + 25 * index, output.shape[0] - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
                cv2.LINE_AA,
            )
