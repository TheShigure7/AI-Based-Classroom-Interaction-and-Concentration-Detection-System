"""Behavior aggregation for classroom actions."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.analysis.attention_analyzer import AttentionAnalyzer
from app.services.analysis.hand_raise_analyzer import HandRaiseAnalyzer
from app.services.analysis.phone_use_analyzer import PhoneUseAnalyzer
from app.services.analysis.sleeping_analyzer import SleepingAnalyzer
from app.services.analysis.talking_analyzer import TalkingAnalyzer, TalkingSubject
from app.services.detection.yolo_detector import DetectionResult
from app.services.pose.mediapipe_estimator import PoseEstimate
from app.services.pose.mediapipe_hands import HandResult, MediaPipeHandsEstimator
from app.services.tracking.student_tracker import TrackedStudent


@dataclass
class BehaviorState:
    """Unified per-student behavior result for a single frame."""

    hand_raised: bool = False
    head_down: bool = False
    phone_risk: bool = False
    sleeping: bool = False
    talking_risk: bool = False


class BehaviorEngine:
    """Compose multiple analyzers into one stable behavior interface.

    Every behavior flag is temporally smoothed: a positive detection must
    persist for *confirm_frames* consecutive frames before the flag turns
    on, and must be absent for *release_frames* consecutive frames before
    it turns off.  This eliminates rapid flickering between states.
    """

    CONFIRM_FRAMES = 10
    RELEASE_FRAMES = 10

    def __init__(
        self,
        hand_raise_analyzer: HandRaiseAnalyzer | None = None,
        attention_analyzer: AttentionAnalyzer | None = None,
        phone_use_analyzer: PhoneUseAnalyzer | None = None,
        sleeping_analyzer: SleepingAnalyzer | None = None,
        talking_analyzer: TalkingAnalyzer | None = None,
    ) -> None:
        self.hand_raise_analyzer = hand_raise_analyzer or HandRaiseAnalyzer()
        self.attention_analyzer = attention_analyzer or AttentionAnalyzer()
        self.phone_use_analyzer = phone_use_analyzer or PhoneUseAnalyzer()
        self.sleeping_analyzer = sleeping_analyzer or SleepingAnalyzer()
        self.talking_analyzer = talking_analyzer or TalkingAnalyzer()

        # Per-student temporal smoothing state
        # track_id -> {behavior_name: consecutive_frame_count}
        self._confirm: dict[str, dict[str, int]] = {}
        self._release: dict[str, dict[str, int]] = {}
        self._active: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_person(
        self,
        person_detection: DetectionResult,
        tracked_student: TrackedStudent,
        phone_detections: list[DetectionResult],
        pose_estimate: PoseEstimate | None,
    ) -> BehaviorState:
        """Return raw (unsmoothed) behavior flags for one detected student."""
        if pose_estimate is None:
            return BehaviorState()

        landmarks = pose_estimate.landmarks
        head_down = self.attention_analyzer.is_head_down(landmarks)

        return BehaviorState(
            hand_raised=self.hand_raise_analyzer.analyze(landmarks),
            head_down=head_down,
            phone_risk=any(
                self.phone_use_analyzer.is_phone_risk(
                    person_detection.bbox,
                    phone_detection.bbox,
                    head_down,
                )
                for phone_detection in phone_detections
            ),
            sleeping=self.sleeping_analyzer.analyze(tracked_student.track_id, landmarks),
        )

    def analyze_scene_talking(
        self,
        person_detections: list[DetectionResult],
        track_assignments: dict[int, TrackedStudent],
        pose_estimates: dict[int, PoseEstimate | None],
    ) -> set[str]:
        """Return track IDs currently at talking risk (scene interaction)."""
        subjects: list[TalkingSubject] = []
        for index, detection in enumerate(person_detections):
            pose_estimate = pose_estimates.get(index)
            if pose_estimate is None:
                continue
            tracked_student = track_assignments[index]
            subjects.append(
                TalkingSubject(
                    track_id=tracked_student.track_id,
                    bbox=detection.bbox,
                    landmarks=pose_estimate.landmarks,
                )
            )
        return self.talking_analyzer.analyze_scene(subjects)

    def apply_behavior_state(
        self,
        detection: DetectionResult,
        tracked_student: TrackedStudent,
        behavior_state: BehaviorState,
    ) -> None:
        """Smooth raw flags and write them to both detection and tracked state."""
        track_id = tracked_student.track_id
        detection.track_id = track_id
        self._ensure_state(track_id)

        raw = {
            "hand_raised": behavior_state.hand_raised,
            "head_down": behavior_state.head_down,
            "phone_risk": behavior_state.phone_risk,
            "sleeping": behavior_state.sleeping,
        }

        for name, detected in raw.items():
            active = self._smooth(track_id, name, detected)
            setattr(detection, name, active)
            setattr(tracked_student, name, active)

        # talking_risk is written later by apply_talking_states()

    def apply_talking_states(
        self,
        person_detections: list[DetectionResult],
        track_assignments: dict[int, TrackedStudent],
        talking_track_ids: set[str],
    ) -> None:
        """Smooth talking-risk states after whole-scene interaction analysis."""
        for index, detection in enumerate(person_detections):
            tracked_student = track_assignments[index]
            track_id = tracked_student.track_id
            self._ensure_state(track_id)

            raw_talking = tracked_student.track_id in talking_track_ids
            active = self._smooth(track_id, "talking_risk", raw_talking)
            detection.talking_risk = active
            tracked_student.talking_risk = active

    # ------------------------------------------------------------------
    # Hand-landmark refinement
    # ------------------------------------------------------------------

    def refine_hand_raise(
        self,
        person_detections: list[DetectionResult],
        track_assignments: dict[int, TrackedStudent],
        hand_results: list[HandResult],
    ) -> None:
        """Confirm hand_raised via MediaPipe Hands finger-state analysis.

        For each student already flagged as hand_raised by the pose-based
        rules, check whether an associated open hand (>=2 fingers extended)
        exists.  If no open hand is found, the flag is downgraded to reduce
        false positives.
        """
        if not hand_results:
            return

        # Build per-student hand associations
        associations = self._associate_hands(person_detections, hand_results)

        for index, detection in enumerate(person_detections):
            if not detection.hand_raised:
                continue

            student_hands = associations.get(index, [])
            if not student_hands:
                # No hand detected near this student → downgrade
                detection.hand_raised = False
                track_assignments[index].hand_raised = False
                continue

            # At least one associated hand should be open
            any_open = any(
                MediaPipeHandsEstimator.is_hand_open(h.landmarks)
                for h in student_hands
            )
            if not any_open:
                detection.hand_raised = False
                track_assignments[index].hand_raised = False

    @staticmethod
    def _associate_hands(
        person_detections: list[DetectionResult],
        hand_results: list[HandResult],
    ) -> dict[int, list[HandResult]]:
        """Map each detected hand to the student it most likely belongs to.

        A hand belongs to a student when the hand bbox center lies inside
        the student bbox or the bboxes overlap enough.
        """
        associations: dict[int, list[HandResult]] = {}

        for hand in hand_results:
            hx = (hand.bbox[0] + hand.bbox[2]) / 2
            hy = (hand.bbox[1] + hand.bbox[3]) / 2

            best_idx = -1
            best_overlap = 0.0

            for idx, det in enumerate(person_detections):
                x1, y1, x2, y2 = det.bbox
                # Hand center inside student bbox → strong association
                if x1 <= hx <= x2 and y1 <= hy <= y2:
                    best_idx = idx
                    break

                # Otherwise use bbox IoU
                iou = _bbox_iou(hand.bbox, det.bbox)
                if iou > best_overlap:
                    best_overlap = iou
                    best_idx = idx

            if best_idx >= 0:
                associations.setdefault(best_idx, []).append(hand)

        return associations


    # ------------------------------------------------------------------
    # Temporal smoothing
    # ------------------------------------------------------------------

    def _ensure_state(self, track_id: str) -> None:
        if track_id not in self._confirm:
            self._confirm[track_id] = {}
            self._release[track_id] = {}
            self._active[track_id] = set()

    def _smooth(self, track_id: str, name: str, detected: bool) -> bool:
        """Apply hysteresis to a single behavior flag.

        Returns the temporally smoothed value.
        """
        confirm = self._confirm[track_id]
        release = self._release[track_id]
        active_set = self._active[track_id]

        if detected:
            confirm[name] = confirm.get(name, 0) + 1
            release[name] = 0
            if confirm[name] >= self.CONFIRM_FRAMES:
                active_set.add(name)
        else:
            confirm[name] = 0
            release[name] = release.get(name, 0) + 1
            if release[name] >= self.RELEASE_FRAMES:
                active_set.discard(name)

        return name in active_set


def _bbox_iou(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> float:
    """Intersection-over-union of two pixel bboxes."""
    xl = max(a[0], b[0])
    yt = max(a[1], b[1])
    xr = min(a[2], b[2])
    yb = min(a[3], b[3])
    if xr <= xl or yb <= yt:
        return 0.0
    inter = (xr - xl) * (yb - yt)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)
