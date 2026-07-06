"""Simple behavior rule helpers for classroom MVP."""

from __future__ import annotations

import math
from typing import Iterable


def landmark_visible(landmark: object, threshold: float = 0.25) -> bool:
    """Return True when a landmark has enough visibility confidence.

    Lowered from 0.4 to 0.25 for classroom settings where students are
    farther from the camera and landmarks have lower visibility scores.
    """
    visibility = float(getattr(landmark, "visibility", 1.0))
    presence = float(getattr(landmark, "presence", 1.0))
    return visibility >= threshold and presence >= threshold


def _arm_angle(
    shoulder: object,
    elbow: object,
    wrist: object,
) -> float:
    """Return the angle (in degrees) at the elbow formed by shoulder-elbow-wrist.

    A small angle (< 90°) means the forearm is bent upward (hand near head).
    A large angle (> 150°) means the arm is extended straight.
    """
    # Vectors: shoulder->elbow and wrist->elbow
    se_x = shoulder.x - elbow.x
    se_y = shoulder.y - elbow.y
    we_x = wrist.x - elbow.x
    we_y = wrist.y - elbow.y

    dot = se_x * we_x + se_y * we_y
    mag_se = math.sqrt(se_x ** 2 + se_y ** 2)
    mag_we = math.sqrt(we_x ** 2 + we_y ** 2)

    if mag_se < 1e-6 or mag_we < 1e-6:
        return 0.0

    cos_angle = max(-1.0, min(1.0, dot / (mag_se * mag_we)))
    return math.degrees(math.acos(cos_angle))


def is_hand_raised_from_landmarks(landmarks: Iterable[object]) -> bool:
    """Detect hand-raising using a multi-tier approach for classroom settings.

    Landmark indexes follow the official MediaPipe pose model:
    11/12 shoulders, 13/14 elbows, 15/16 wrists, 0 nose.

    Three tiers, from strict to lenient:
    1. High-confidence: wrist above shoulder + elbow near shoulder + wrist near nose
    2. Angle-based: arm bent upward (angle < 120°) + wrist above shoulder
    3. Fallback: wrist clearly above shoulder level, even with uncertain elbow
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

    return _is_arm_raised(
        nose, left_shoulder, left_elbow, left_wrist
    ) or _is_arm_raised(
        nose, right_shoulder, right_elbow, right_wrist
    )


def _is_arm_raised(
    nose: object,
    shoulder: object,
    elbow: object,
    wrist: object,
) -> bool:
    """Multi-tier hand-raise check for a single arm."""

    # All four key landmarks should be minimally visible
    if not all(landmark_visible(pt) for pt in (nose, shoulder, elbow, wrist)):
        return False

    # --- Tier 1: High-confidence geometric check (relaxed from original) ---
    # Wrist is above shoulder, elbow is not too low, wrist is near or above nose
    tier1 = (
        wrist.y < shoulder.y
        and elbow.y < shoulder.y + 0.08
        and wrist.y < nose.y + 0.12
    )
    if tier1:
        return True

    # --- Tier 2: Angle-based check ---
    # Arm is bent upward (elbow angle < 120°) and wrist is above shoulder level
    angle = _arm_angle(shoulder, elbow, wrist)
    return (
        angle < 120.0
        and wrist.y < shoulder.y + 0.05
    )


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


def head_turn_direction_from_landmarks(landmarks: Iterable[object]) -> int:
    """Estimate coarse head turn direction from nose offset against shoulder center.

    Returns:
    -1: turned left
     0: no strong side turn
     1: turned right
    """

    landmark_list = list(landmarks)
    if len(landmark_list) < 13:
        return 0

    nose = landmark_list[0]
    left_shoulder = landmark_list[11]
    right_shoulder = landmark_list[12]
    if not all(landmark_visible(point) for point in (nose, left_shoulder, right_shoulder)):
        return 0

    shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2.0
    shoulder_span = abs(left_shoulder.x - right_shoulder.x)
    if shoulder_span < 0.08:
        return 0

    turn_ratio = (nose.x - shoulder_center_x) / shoulder_span
    if turn_ratio > 0.18:
        return 1
    if turn_ratio < -0.18:
        return -1
    return 0


def are_students_close_for_talking(
    bbox_a: tuple[int, int, int, int],
    bbox_b: tuple[int, int, int, int],
) -> bool:
    """Return whether two detected students are close enough for a talking interaction."""

    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    a_center_x = (ax1 + ax2) / 2.0
    b_center_x = (bx1 + bx2) / 2.0
    a_center_y = (ay1 + ay2) / 2.0
    b_center_y = (by1 + by2) / 2.0

    avg_width = ((ax2 - ax1) + (bx2 - bx1)) / 2.0
    avg_height = ((ay2 - ay1) + (by2 - by1)) / 2.0
    horizontal_distance = abs(a_center_x - b_center_x)
    vertical_distance = abs(a_center_y - b_center_y)

    return horizontal_distance <= avg_width * 1.6 and vertical_distance <= avg_height * 0.45
