"""Minimal MediaPipe pose estimation service for classroom MVP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlretrieve

import cv2
import mediapipe as mp
import numpy as np


@dataclass
class PoseEstimate:
    """Pose output for a single detected person ROI."""

    landmarks: list[object]


class MediaPipePoseEstimator:
    """Loads a MediaPipe pose task and runs it on person crops."""

    MODEL_URL = (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
    )

    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path or self._default_model_path()
        self._ensure_model()
        self.landmarker = self._create_landmarker()

    def _default_model_path(self) -> Path:
        project_root = Path(__file__).resolve().parents[4]
        return project_root / "models" / "weights" / "pose_landmarker_lite.task"

    def _ensure_model(self) -> None:
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        if self.model_path.exists():
            return

        urlretrieve(self.MODEL_URL, self.model_path)

    def _create_landmarker(self) -> object:
        try:
            model_bytes = self.model_path.read_bytes()
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Pose model file not found: {self.model_path}"
            ) from exc

        base_options = mp.tasks.BaseOptions(model_asset_buffer=model_bytes)
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        try:
            return mp.tasks.vision.PoseLandmarker.create_from_options(options)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "MediaPipe pose model initialization failed. "
                "The model file may be missing or unreadable."
            ) from exc

    def estimate_person_pose(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int],
    ) -> PoseEstimate | None:
        """Run pose estimation on a single person crop."""
        x1, y1, x2, y2 = bbox
        height, width = frame.shape[:2]
        x1 = max(0, min(x1, width - 1))
        x2 = max(1, min(x2, width))
        y1 = max(0, min(y1, height - 1))
        y2 = max(1, min(y2, height))

        if x2 <= x1 or y2 <= y1:
            return None

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        rgb_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_roi)
        result = self.landmarker.detect(mp_image)

        if not getattr(result, "pose_landmarks", None):
            return None

        return PoseEstimate(landmarks=list(result.pose_landmarks[0]))
