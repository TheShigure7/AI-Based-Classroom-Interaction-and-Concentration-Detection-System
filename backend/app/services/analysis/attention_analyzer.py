"""Attention analysis helpers with time-based scoring."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.services.analysis.behavior_rules import is_head_down_from_landmarks
from app.services.tracking.student_tracker import TrackedStudent


@dataclass
class AttentionSummary:
    """Aggregated attention metrics for current frame."""

    average_score: int = 0
    low_attention_count: int = 0


class AttentionAnalyzer:
    """Analyze pose landmarks for attention-related signals.

    All deltas are time-based (per second).  The scorer uses
    ``time.perf_counter()`` to measure real elapsed seconds between
    consecutive calls for the same student, so scores are independent of
    camera / inference frame rate.
    """

    LOW_ATTENTION_THRESHOLD = 60

    # --- per-second rates ---
    NORMAL_RATE = 2.0            # +2 / s  (no negative behaviour)
    TALKING_RISK_RATE = -3.0     # -3 / s
    PHONE_RISK_RATE = -5.0       # -5 / s

    # --- hand-raise: one-shot bonus ---
    HAND_RAISE_BONUS = 10.0      # +10  (one-time)
    HAND_RAISE_COOLDOWN = 10.0   # 10 s cooldown before next bonus

    # --- head-down progressive penalty ---
    HD_FIRST_SEC_RATE = -1.0     # 1st second
    HD_SECOND_SEC_RATE = -2.0    # 2nd second
    HD_STEADY_RATE = -3.0        # 3rd second and onward

    def is_head_down(self, landmarks: list[object]) -> bool:
        """Return whether the pose landmarks indicate head-down posture."""
        return is_head_down_from_landmarks(landmarks)

    def update_attention_score(self, student: TrackedStudent) -> int:
        """Update a student's attention score using time-based deltas."""
        now = time.perf_counter()

        # --- time delta since last update (clamped for first frame) ---
        dt = now - student.last_score_update_time if student.last_score_update_time > 0 else 0.0
        if dt <= 0 or dt > 1.0:
            dt = 1.0 / 30  # assume ~30 FPS for the very first frame

        score = student.attention_score

        # --- hand_raised: one-shot +10, 10 s cooldown ---
        if student.hand_raised:
            if now - student.last_hand_raise_bonus_time >= self.HAND_RAISE_COOLDOWN:
                score += self.HAND_RAISE_BONUS
                student.last_hand_raise_bonus_time = now

        # --- head_down: progressive penalty ---
        if student.head_down:
            if student.head_down_start_time is None:
                student.head_down_start_time = now
            hd_elapsed = now - student.head_down_start_time
            if hd_elapsed < 1.0:
                hd_rate = self.HD_FIRST_SEC_RATE
            elif hd_elapsed < 2.0:
                hd_rate = self.HD_SECOND_SEC_RATE
            else:
                hd_rate = self.HD_STEADY_RATE
            score += hd_rate * dt
        else:
            student.head_down_start_time = None

        # --- phone_risk ---
        if student.phone_risk:
            score += self.PHONE_RISK_RATE * dt

        # --- talking_risk ---
        if student.talking_risk:
            score += self.TALKING_RISK_RATE * dt

        # --- normal: reward when no negative behaviour is active ---
        if (
            not student.head_down
            and not student.phone_risk
            and not student.talking_risk
        ):
            score += self.NORMAL_RATE * dt

        student.attention_score = max(0.0, min(100.0, score))
        student.last_score_update_time = now
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
