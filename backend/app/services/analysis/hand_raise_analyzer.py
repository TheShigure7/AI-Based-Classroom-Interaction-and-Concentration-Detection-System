"""Hand raise analysis helpers."""

from __future__ import annotations

from app.services.analysis.behavior_rules import is_hand_raised_from_landmarks


class HandRaiseAnalyzer:
    """Analyze pose landmarks and determine whether a hand is raised."""

    def analyze(self, landmarks: list[object]) -> bool:
        """Return whether the current landmark set indicates a raised hand."""
        return is_hand_raised_from_landmarks(landmarks)
