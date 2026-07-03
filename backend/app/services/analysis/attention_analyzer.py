"""Attention analysis helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.analysis.behavior_rules import is_head_down_from_landmarks
from app.services.tracking.student_tracker import TrackedStudent


@dataclass
class AttentionSummary:
    """Aggregated attention metrics for current frame."""

    average_score: int = 0
    low_attention_count: int = 0


class AttentionAnalyzer:
    """Analyze pose landmarks for early attention-related signals."""

    LOW_ATTENTION_THRESHOLD = 60

    def is_head_down(self, landmarks: list[object]) -> bool:
        """Return whether the pose landmarks indicate head-down posture."""
        return is_head_down_from_landmarks(landmarks)

    def update_attention_score(self, student: TrackedStudent) -> int:
        """Update a student's attention score using current per-frame states."""
        score = student.attention_score

        if student.sleeping:
            score -= 1.2
        elif student.head_down:
            score -= 0.35
        if student.phone_risk:
            score -= 0.9
        if student.talking_risk:
            score -= 0.45
        if student.hand_raised:
            score += 0.2
        if (
            not student.head_down
            and not student.phone_risk
            and not student.sleeping
            and not student.talking_risk
        ):
            score += 0.12

        student.attention_score = max(0.0, min(100.0, score))
        return round(student.attention_score)

    def summarize(self, students: list[TrackedStudent]) -> AttentionSummary:
        """Compute class-level attention metrics."""
        if not students:
            return AttentionSummary()

        total = sum(student.attention_score for student in students)
        low_attention_count = sum(
            1 for student in students if student.attention_score < self.LOW_ATTENTION_THRESHOLD
        )
        average_score = round(total / len(students))
        return AttentionSummary(
            average_score=average_score,
            low_attention_count=low_attention_count,
        )
