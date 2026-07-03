"""Sleeping-risk analysis with temporal smoothing."""

from __future__ import annotations

from app.services.analysis.behavior_rules import (
    calculate_motion_delta,
    extract_sleep_signature,
    is_sleeping_posture_from_landmarks,
)


class SleepingAnalyzer:
    """Estimate sleeping risk from pose posture and low motion over time."""

    CANDIDATE_FRAMES = 8
    RELEASE_FRAMES = 3
    LOW_MOTION_THRESHOLD = 0.025

    def __init__(self) -> None:
        self._candidate_counts: dict[str, int] = {}
        self._release_counts: dict[str, int] = {}
        self._sleeping_state: dict[str, bool] = {}
        self._previous_signatures: dict[str, tuple[float, ...]] = {}

    def analyze(self, track_id: str, landmarks: list[object] | None) -> bool:
        """Return a smoothed sleeping-risk state for one tracked student."""
        if landmarks is None:
            return self._step_release(track_id)

        posture_risk = is_sleeping_posture_from_landmarks(landmarks)
        signature = extract_sleep_signature(landmarks)
        previous_signature = self._previous_signatures.get(track_id)
        motion_delta = calculate_motion_delta(previous_signature, signature)
        low_motion = (
            signature is not None
            and previous_signature is not None
            and motion_delta <= self.LOW_MOTION_THRESHOLD
        )

        if signature is not None:
            self._previous_signatures[track_id] = signature

        if posture_risk and low_motion:
            self._candidate_counts[track_id] = self._candidate_counts.get(track_id, 0) + 1
            self._release_counts[track_id] = 0
            if self._candidate_counts[track_id] >= self.CANDIDATE_FRAMES:
                self._sleeping_state[track_id] = True
        else:
            self._candidate_counts[track_id] = 0
            self._step_release(track_id)

        return self._sleeping_state.get(track_id, False)

    def _step_release(self, track_id: str) -> bool:
        self._release_counts[track_id] = self._release_counts.get(track_id, 0) + 1
        if self._release_counts[track_id] >= self.RELEASE_FRAMES:
            self._sleeping_state[track_id] = False
        return self._sleeping_state.get(track_id, False)
