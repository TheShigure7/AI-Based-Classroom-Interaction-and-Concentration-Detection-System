"""Talking-risk analysis using nearby pair interactions."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.analysis.behavior_rules import (
    are_students_close_for_talking,
    head_turn_direction_from_landmarks,
)


@dataclass
class TalkingSubject:
    """Minimal scene subject used for pair interaction analysis."""

    track_id: str
    bbox: tuple[int, int, int, int]
    landmarks: list[object]


class TalkingAnalyzer:
    """Estimate talking risk by checking whether nearby students face each other."""

    CANDIDATE_FRAMES = 1    # raw per-frame signal; smoothing is handled by BehaviorEngine
    RELEASE_FRAMES = 1

    def __init__(self) -> None:
        self._pair_candidate_counts: dict[tuple[str, str], int] = {}
        self._pair_release_counts: dict[tuple[str, str], int] = {}
        self._active_pairs: set[tuple[str, str]] = set()

    def analyze_scene(self, subjects: list[TalkingSubject]) -> set[str]:
        """Return track IDs currently considered at talking risk."""
        current_pairs: set[tuple[str, str]] = set()

        for left_index, left_subject in enumerate(subjects):
            for right_subject in subjects[left_index + 1 :]:
                pair_key = tuple(sorted((left_subject.track_id, right_subject.track_id)))
                is_candidate = self._pair_is_talking_candidate(left_subject, right_subject)
                if is_candidate:
                    self._pair_candidate_counts[pair_key] = (
                        self._pair_candidate_counts.get(pair_key, 0) + 1
                    )
                    self._pair_release_counts[pair_key] = 0
                    if self._pair_candidate_counts[pair_key] >= self.CANDIDATE_FRAMES:
                        self._active_pairs.add(pair_key)
                else:
                    self._pair_candidate_counts[pair_key] = 0
                    self._pair_release_counts[pair_key] = (
                        self._pair_release_counts.get(pair_key, 0) + 1
                    )
                    if self._pair_release_counts[pair_key] >= self.RELEASE_FRAMES:
                        self._active_pairs.discard(pair_key)

                if pair_key in self._active_pairs:
                    current_pairs.add(pair_key)

        stale_pairs = set(self._active_pairs)
        stale_pairs.difference_update(current_pairs)
        for pair_key in stale_pairs:
            self._pair_release_counts[pair_key] = self._pair_release_counts.get(pair_key, 0) + 1
            if self._pair_release_counts[pair_key] >= self.RELEASE_FRAMES:
                self._active_pairs.discard(pair_key)

        risky_track_ids: set[str] = set()
        for left_track_id, right_track_id in self._active_pairs:
            risky_track_ids.add(left_track_id)
            risky_track_ids.add(right_track_id)
        return risky_track_ids

    @staticmethod
    def _pair_is_talking_candidate(
        left_subject: TalkingSubject,
        right_subject: TalkingSubject,
    ) -> bool:
        if not are_students_close_for_talking(left_subject.bbox, right_subject.bbox):
            return False

        left_center_x = (left_subject.bbox[0] + left_subject.bbox[2]) / 2.0
        right_center_x = (right_subject.bbox[0] + right_subject.bbox[2]) / 2.0
        left_direction = head_turn_direction_from_landmarks(left_subject.landmarks)
        right_direction = head_turn_direction_from_landmarks(right_subject.landmarks)

        if left_center_x <= right_center_x:
            return left_direction == 1 and right_direction == -1
        return left_direction == -1 and right_direction == 1
