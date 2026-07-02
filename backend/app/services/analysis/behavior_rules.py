"""Simple behavior rule helpers for classroom MVP."""

from __future__ import annotations

from typing import Iterable


def landmark_visible(landmark: object, threshold: float = 0.4) -> bool:
    """Return True when a landmark has enough visibility confidence."""
    visibility = float(getattr(landmark, "visibility", 1.0))
    presence = float(getattr(landmark, "presence", 1.0))
    return visibility >= threshold and presence >= threshold


def is_hand_raised_from_landmarks(landmarks: Iterable[object]) -> bool:
    """Apply a lightweight hand-raise rule to pose landmarks.

    Landmark indexes follow the official MediaPipe pose model:
    11/12 shoulders, 13/14 elbows, 15/16 wrists, 0 nose.
    """

    landmark_list = list(landmarks)
    if len(landmark_list) < 17:
        return False

    nose = landmark_list[0]
    left_shoulder = landmark_list[11]
    right_shoulder = landmark_list[12]
    left_elbow = landmark_list[13]
    right_elbow = landmark_list[14]
    left_wrist = landmark_list[15]
    right_wrist = landmark_list[16]

    left_ready = all(
        landmark_visible(point)
        for point in (nose, left_shoulder, left_elbow, left_wrist)
    )
    right_ready = all(
        landmark_visible(point)
        for point in (nose, right_shoulder, right_elbow, right_wrist)
    )

    left_raised = left_ready and (
        left_wrist.y < left_shoulder.y - 0.03
        and left_elbow.y < left_shoulder.y + 0.02
        and left_wrist.y < nose.y + 0.05
    )
    right_raised = right_ready and (
        right_wrist.y < right_shoulder.y - 0.03
        and right_elbow.y < right_shoulder.y + 0.02
        and right_wrist.y < nose.y + 0.05
    )

    return left_raised or right_raised


def is_head_down_from_landmarks(landmarks: Iterable[object]) -> bool:
    """Apply a lightweight head-down rule using nose and shoulder landmarks."""

    landmark_list = list(landmarks)
    if len(landmark_list) < 13:
        return False

    nose = landmark_list[0]
    left_shoulder = landmark_list[11]
    right_shoulder = landmark_list[12]

    if not all(landmark_visible(point) for point in (nose, left_shoulder, right_shoulder)):
        return False

    shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2.0
    shoulder_span = abs(left_shoulder.x - right_shoulder.x)
    if shoulder_span < 0.08:
        return False

    # If the nose drops too close to the shoulder line while the shoulders remain visible,
    # treat it as a first-pass head-down signal.
    nose_to_shoulder_gap = shoulder_center_y - nose.y
    return nose_to_shoulder_gap < 0.12


def is_phone_risk(
    person_bbox: tuple[int, int, int, int],
    phone_bbox: tuple[int, int, int, int],
    head_down: bool,
) -> bool:
    """Return whether a phone is likely associated with a student's distraction.

    Rule:
    - phone center should fall inside the student box or very close to its lower half
    - and the student should also be in a head-down posture
    """

    if not head_down:
        return False

    px1, py1, px2, py2 = person_bbox
    fx1, fy1, fx2, fy2 = phone_bbox

    phone_center_x = (fx1 + fx2) / 2.0
    phone_center_y = (fy1 + fy2) / 2.0
    person_width = px2 - px1
    person_height = py2 - py1

    inside_person = px1 <= phone_center_x <= px2 and py1 <= phone_center_y <= py2
    near_lower_body = (
        px1 - person_width * 0.1 <= phone_center_x <= px2 + person_width * 0.1
        and py1 + person_height * 0.35 <= phone_center_y <= py2 + person_height * 0.15
    )

    return inside_person or near_lower_body
