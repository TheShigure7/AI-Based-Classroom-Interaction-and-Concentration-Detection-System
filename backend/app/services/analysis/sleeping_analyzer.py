"""Sleeping-risk analysis — head on hands, motion-based."""

from __future__ import annotations

from app.services.analysis.behavior_rules import (
    calculate_motion_delta,
    extract_sleep_signature,
    is_sleeping_posture_from_landmarks,
)


class SleepingAnalyzer:
    """Check per-frame sleeping posture + low body motion.

    No temporal smoothing — that is handled by BehaviorEngine.
    """

    LOW_MOTION_THRESHOLD = 0.025

    def __init__(self) -> None:
        self._prev: dict[str, tuple[float, ...]] = {}

    def analyze(self, track_id: str, landmarks: list[object] | None) -> bool:
        """Return True when both posture and low-motion conditions are met."""
        if landmarks is None:
            return False

        if not is_sleeping_posture_from_landmarks(landmarks):
            self._prev.pop(track_id, None)
            return False

        sig = extract_sleep_signature(landmarks)
        if sig is None:
            return False

        prev_sig = self._prev.get(track_id)
        self._prev[track_id] = sig

        if prev_sig is None:
            return False  # need at least one previous frame to compare motion

        motion = calculate_motion_delta(prev_sig, sig)
        return motion <= self.LOW_MOTION_THRESHOLD
