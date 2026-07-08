"""MediaPipe Hands landmarker for finger-state analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import urlretrieve

import cv2
import mediapipe as mp
import numpy as np


@dataclass
class HandResult:
    """One detected hand with 21 landmarks and handedness."""

    landmarks: list[object]   # 21 MediaPipe NormalizedLandmark objects
    handedness: str           # "Left" or "Right"
    score: float              # detection confidence
    bbox: tuple[int, int, int, int]  # pixel bbox (x1, y1, x2, y2)


@dataclass
class FingerState:
    """Per-finger extension flags."""

    thumb: bool = False
    index: bool = False
    middle: bool = False
    ring: bool = False
    pinky: bool = False

    @property
    def extended_count(self) -> int:
        return sum((self.thumb, self.index, self.middle, self.ring, self.pinky))


class MediaPipeHandsEstimator:
    """Loads the MediaPipe Hand Landmarker and returns per-hand landmarks."""

    MODEL_URL = (
        "https://storage.googleapis.com/mediapipe-models/"
        "hand_landmarker/hand_landmarker/float16/latest/"
        "hand_landmarker.task"
    )

    # MediaPipe hand topology — fingertip and PIP joint indices
    _FINGER_TIPS = (4, 8, 12, 16, 20)    # thumb, index, middle, ring, pinky TIP
    _FINGER_PIPS = (2, 6, 10, 14, 18)    # thumb IP, others PIP

    FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")

    def __init__(
        self,
        model_path: Path | None = None,
        detection_max_side: int = 640,
    ) -> None:
        self.model_path = model_path or self._default_model_path()
        self.detection_max_side = detection_max_side
        self._ensure_model()
        self.landmarker = self._create_landmarker()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _default_model_path(self) -> Path:
        project_root = Path(__file__).resolve().parents[4]
        return project_root / "models" / "weights" / "hand_landmarker.task"

    def _ensure_model(self) -> None:
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        if self.model_path.exists():
            return
        urlretrieve(self.MODEL_URL, self.model_path)

    def _create_landmarker(self) -> object:
        model_bytes = self.model_path.read_bytes()
        base_options = mp.tasks.BaseOptions(model_asset_buffer=model_bytes)
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_hands=10,
            min_hand_detection_confidence=0.3,
            min_hand_presence_confidence=0.3,
            min_tracking_confidence=0.3,
        )
        return mp.tasks.vision.HandLandmarker.create_from_options(options)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_hands(self, frame: np.ndarray) -> list[HandResult]:
        """Run hand landmark detection on a BGR frame (or person ROI)."""
        processed_frame, scale_x, scale_y = self._prepare_frame(frame)
        rgb = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect(mp_image)

        hands: list[HandResult] = []
        if not result.hand_landmarks:
            return hands

        h, w = processed_frame.shape[:2]
        for idx, landmarks in enumerate(result.hand_landmarks):
            handedness = result.handedness[idx][0]
            score = float(result.handedness[idx][0].score)

            # Compute bbox in frame pixel coordinates
            xs = [lm.x * w for lm in landmarks]
            ys = [lm.y * h for lm in landmarks]
            x1, x2 = int(min(xs) * scale_x), int(max(xs) * scale_x)
            y1, y2 = int(min(ys) * scale_y), int(max(ys) * scale_y)

            hands.append(HandResult(
                landmarks=list(landmarks),
                handedness=handedness.display_name or handedness.category_name,
                score=score,
                bbox=(x1, y1, x2, y2),
            ))

        return hands

    def _prepare_frame(self, frame: np.ndarray) -> tuple[np.ndarray, float, float]:
        """Downscale large frames before hand detection to reduce inference cost."""
        if self.detection_max_side <= 0:
            return frame, 1.0, 1.0

        original_h, original_w = frame.shape[:2]
        longest_side = max(original_h, original_w)
        if longest_side <= self.detection_max_side:
            return frame, 1.0, 1.0

        resize_ratio = self.detection_max_side / float(longest_side)
        resized_w = max(1, int(original_w * resize_ratio))
        resized_h = max(1, int(original_h * resize_ratio))
        resized = cv2.resize(frame, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
        scale_x = original_w / float(resized_w)
        scale_y = original_h / float(resized_h)
        return resized, scale_x, scale_y

    # ------------------------------------------------------------------
    # Finger state
    # ------------------------------------------------------------------

    @classmethod
    def get_finger_state(cls, hand_landmarks: list[object]) -> FingerState:
        """Return which fingers are extended (not curled).

        A finger is considered extended when its TIP is above its PIP
        in image space (Y increases downward), i.e. the finger is
        pointing up rather than curled into a fist.
        """
        states = []
        for tip_idx, pip_idx in zip(cls._FINGER_TIPS, cls._FINGER_PIPS):
            tip = hand_landmarks[tip_idx]
            pip = hand_landmarks[pip_idx]
            # TIP above PIP → finger pointing upward / extended
            extended = tip.y < pip.y - 0.01
            states.append(extended)

        return FingerState(*states)

    @classmethod
    def is_hand_open(cls, hand_landmarks: list[object], min_fingers: int = 2) -> bool:
        """Return True when the hand appears open (enough fingers extended)."""
        state = cls.get_finger_state(hand_landmarks)
        return state.extended_count >= min_fingers
