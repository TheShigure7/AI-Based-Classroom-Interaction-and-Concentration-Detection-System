"""Behavior aggregation for classroom actions."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.analysis.attention_analyzer import AttentionAnalyzer
from app.services.analysis.hand_raise_analyzer import HandRaiseAnalyzer
from app.services.analysis.phone_use_analyzer import PhoneUseAnalyzer
from app.services.detection.yolo_detector import DetectionResult
from app.services.pose.mediapipe_estimator import PoseEstimate
from app.services.tracking.student_tracker import TrackedStudent


@dataclass
class BehaviorState:
    """Unified per-student behavior result for a single frame."""

    hand_raised: bool = False
    head_down: bool = False
    phone_risk: bool = False


class BehaviorEngine:
    """Compose multiple analyzers into one stable behavior interface."""

    def __init__(
        self,
        hand_raise_analyzer: HandRaiseAnalyzer | None = None,
        attention_analyzer: AttentionAnalyzer | None = None,
        phone_use_analyzer: PhoneUseAnalyzer | None = None,
    ) -> None:
        self.hand_raise_analyzer = hand_raise_analyzer or HandRaiseAnalyzer()
        self.attention_analyzer = attention_analyzer or AttentionAnalyzer()
        self.phone_use_analyzer = phone_use_analyzer or PhoneUseAnalyzer()

    def analyze_person(
        self,
        person_detection: DetectionResult,
        phone_detections: list[DetectionResult],
        pose_estimate: PoseEstimate | None,
    ) -> BehaviorState:
        """Return aggregated behavior flags for one detected student."""
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
        )

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

        tracked_student.hand_raised = behavior_state.hand_raised
        tracked_student.head_down = behavior_state.head_down
        tracked_student.phone_risk = behavior_state.phone_risk
