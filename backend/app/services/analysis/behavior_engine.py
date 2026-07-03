"""Behavior aggregation for classroom actions."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.analysis.attention_analyzer import AttentionAnalyzer
from app.services.analysis.hand_raise_analyzer import HandRaiseAnalyzer
from app.services.analysis.phone_use_analyzer import PhoneUseAnalyzer
from app.services.analysis.sleeping_analyzer import SleepingAnalyzer
from app.services.analysis.talking_analyzer import TalkingAnalyzer, TalkingSubject
from app.services.detection.yolo_detector import DetectionResult
from app.services.pose.mediapipe_estimator import PoseEstimate
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
    """Compose multiple analyzers into one stable behavior interface."""

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

    def analyze_person(
        self,
        person_detection: DetectionResult,
        tracked_student: TrackedStudent,
        phone_detections: list[DetectionResult],
        pose_estimate: PoseEstimate | None,
    ) -> BehaviorState:
        """Return aggregated behavior flags for one detected student."""
        if pose_estimate is None:
            return BehaviorState(
                sleeping=self.sleeping_analyzer.analyze(tracked_student.track_id, None),
            )

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
        """Return track IDs currently at talking risk from whole-scene interactions."""

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

    @staticmethod
    def apply_behavior_state(
        detection: DetectionResult,
        tracked_student: TrackedStudent,
        behavior_state: BehaviorState,
    ) -> None:
        """Write behavior flags back to both current detection and tracked state."""
        detection.hand_raised = behavior_state.hand_raised
        detection.head_down = behavior_state.head_down
        detection.phone_risk = behavior_state.phone_risk
        detection.sleeping = behavior_state.sleeping
        detection.talking_risk = behavior_state.talking_risk

        tracked_student.hand_raised = behavior_state.hand_raised
        tracked_student.head_down = behavior_state.head_down
        tracked_student.phone_risk = behavior_state.phone_risk
        tracked_student.sleeping = behavior_state.sleeping
        tracked_student.talking_risk = behavior_state.talking_risk

    @staticmethod
    def apply_talking_states(
        person_detections: list[DetectionResult],
        track_assignments: dict[int, TrackedStudent],
        talking_track_ids: set[str],
    ) -> None:
        """Write talking-risk states after whole-scene interaction analysis."""

        for index, detection in enumerate(person_detections):
            tracked_student = track_assignments[index]
            talking_risk = tracked_student.track_id in talking_track_ids
            detection.talking_risk = talking_risk
            tracked_student.talking_risk = talking_risk
