"""Simple anonymous student tracking for classroom MVP."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrackedStudent:
    """Persistent anonymous student state across nearby frames."""

    track_id: str
    bbox: tuple[int, int, int, int]
    attention_score: float = 100.0
    missed_frames: int = 0
    hand_raised: bool = False
    head_down: bool = False
    phone_risk: bool = False


class StudentTracker:
    """Assigns stable anonymous IDs using bbox overlap and center distance."""

    def __init__(self, max_missed_frames: int = 8) -> None:
        self.max_missed_frames = max_missed_frames
        self.students: dict[str, TrackedStudent] = {}
        self._next_id = 1

    def update(
        self,
        person_bboxes: list[tuple[int, int, int, int]],
    ) -> dict[int, TrackedStudent]:
        """Match current person boxes to tracked students.

        Returns a mapping from current detection index to tracked student.
        """

        assignments: dict[int, TrackedStudent] = {}
        unmatched_tracks = set(self.students.keys())

        for index, bbox in enumerate(person_bboxes):
            best_track_id = None
            best_score = -1.0

            for track_id in list(unmatched_tracks):
                tracked = self.students[track_id]
                iou_score = self._iou(bbox, tracked.bbox)
                distance_score = 1.0 / (1.0 + self._center_distance(bbox, tracked.bbox))
                score = iou_score * 2.0 + distance_score

                if iou_score < 0.1 and distance_score < 0.02:
                    continue

                if score > best_score:
                    best_score = score
                    best_track_id = track_id

            if best_track_id is None:
                tracked = self._create_student(bbox)
            else:
                tracked = self.students[best_track_id]
                tracked.bbox = bbox
                tracked.missed_frames = 0
                unmatched_tracks.remove(best_track_id)

            assignments[index] = tracked

        for track_id in list(unmatched_tracks):
            tracked = self.students[track_id]
            tracked.missed_frames += 1
            if tracked.missed_frames > self.max_missed_frames:
                del self.students[track_id]

        return assignments

    def _create_student(self, bbox: tuple[int, int, int, int]) -> TrackedStudent:
        track_id = f"S{self._next_id}"
        self._next_id += 1
        student = TrackedStudent(track_id=track_id, bbox=bbox)
        self.students[track_id] = student
        return student

    @staticmethod
    def _center_distance(
        bbox_a: tuple[int, int, int, int],
        bbox_b: tuple[int, int, int, int],
    ) -> float:
        ax = (bbox_a[0] + bbox_a[2]) / 2.0
        ay = (bbox_a[1] + bbox_a[3]) / 2.0
        bx = (bbox_b[0] + bbox_b[2]) / 2.0
        by = (bbox_b[1] + bbox_b[3]) / 2.0
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    @staticmethod
    def _iou(
        bbox_a: tuple[int, int, int, int],
        bbox_b: tuple[int, int, int, int],
    ) -> float:
        x_left = max(bbox_a[0], bbox_b[0])
        y_top = max(bbox_a[1], bbox_b[1])
        x_right = min(bbox_a[2], bbox_b[2])
        y_bottom = min(bbox_a[3], bbox_b[3])

        if x_right <= x_left or y_bottom <= y_top:
            return 0.0

        intersection = (x_right - x_left) * (y_bottom - y_top)
        area_a = (bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1])
        area_b = (bbox_b[2] - bbox_b[0]) * (bbox_b[3] - bbox_b[1])
        union = area_a + area_b - intersection

        if union <= 0:
            return 0.0

        return intersection / union
