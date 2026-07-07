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


def is_hand_raised_from_landmarks(landmarks: Iterable[object]) -> bool:
    """Detect hand-raising: wrist above shoulder, elbow up, wrist near nose,
    and fingers above wrist (hand pointing upward)."""

    landmark_list = list(landmarks)
    if len(landmark_list) < 21:
        return False

    nose = landmark_list[0]
    left_shoulder = landmark_list[11]
    right_shoulder = landmark_list[12]
    left_elbow = landmark_list[13]
    right_elbow = landmark_list[14]
    left_wrist = landmark_list[15]
    right_wrist = landmark_list[16]
    left_pinky = landmark_list[17]
    right_pinky = landmark_list[18]
    left_index = landmark_list[19]
    right_index = landmark_list[20]

    return _arm_raised(
        nose, left_shoulder, left_elbow, left_wrist, left_pinky, left_index
    ) or _arm_raised(
        nose, right_shoulder, right_elbow, right_wrist, right_pinky, right_index
    )


def _arm_raised(
    nose: object,
    shoulder: object,
    elbow: object,
    wrist: object,
    pinky: object,
    index: object,
) -> bool:
    """Two-rule hand-raise: either full-arm or simple finger-up."""
    if not all(landmark_visible(pt) for pt in (nose, shoulder, elbow, wrist, pinky, index)):
        return False

    fingers_up = pinky.y < wrist.y or index.y < wrist.y
    wrist_high = wrist.y < shoulder.y

    if not (wrist_high and fingers_up):
        return False

    # Rule 1 (strict): full arm — elbow up + wrist near nose
    if elbow.y < shoulder.y + 0.08 and wrist.y < nose.y + 0.12:
        return True

    # Rule 2 (lenient): wrist above shoulder + fingers above wrist
    return True


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


# ---------------------------------------------------------------------------
# Sleeping: head resting on hand(s) placed flat on desk
# ---------------------------------------------------------------------------


def is_sleeping_posture_from_landmarks(landmarks: Iterable[object]) -> bool:
    """Detect sleeping posture from two independent signals.

    Mode A – Head resting on hand(s) placed flat on the desk:
      wrist at/below elbow + wrist below shoulder + nose close to wrist.

    Mode B – Eyes closed:
      MediaPipe pose model eye landmarks (indices 2 & 5) drop to very low
      visibility when the eyes are shut because the iris / eye contour
      becomes undetectable.  This provides a lightweight approximation of
      eye-closed detection without an extra face-landmark model.
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

    if not all(landmark_visible(pt) for pt in (nose, left_shoulder, right_shoulder)):
        return False

    # --- Mode A: head on hands ---
    if _head_on_desk_hand(nose, left_shoulder, left_elbow, left_wrist):
        return True
    if _head_on_desk_hand(nose, right_shoulder, right_elbow, right_wrist):
        return True

    # --- Mode B: eyes closed ---
    if _eyes_closed(landmark_list):
        return True

    return False


def _eyes_closed(landmark_list: list[object]) -> bool:
    """Return True when both eyes appear closed.

    Uses MediaPipe Pose model landmarks: 2 = left eye, 5 = right eye.
    When the eyes are shut the iris texture disappears, causing the eye
    landmarks' visibility to drop sharply.
    """
    left_eye = landmark_list[2]
    right_eye = landmark_list[5]

    left_vis = float(getattr(left_eye, "visibility", 1.0))
    right_vis = float(getattr(right_eye, "visibility", 1.0))

    return left_vis < 0.2 and right_vis < 0.2


def _head_on_desk_hand(
    nose: object,
    shoulder: object,
    elbow: object,
    wrist: object,
) -> bool:
    """Single-arm check: hand on desk + head resting on it."""
    if not all(landmark_visible(pt) for pt in (elbow, wrist)):
        return False

    # Hand on desk surface: wrist not higher than elbow.
    hand_on_desk = wrist.y >= elbow.y - 0.02

    # Wrist below shoulder level (not raised).
    wrist_below_shoulder = wrist.y > shoulder.y

    # Head close to hand in 2-D image space.
    dx = float(nose.x) - float(wrist.x)
    dy = float(nose.y) - float(wrist.y)
    nose_to_wrist = math.sqrt(dx * dx + dy * dy)
    head_near_hand = nose_to_wrist < 0.22

    return hand_on_desk and wrist_below_shoulder and head_near_hand


def extract_sleep_signature(landmarks: Iterable[object]) -> tuple[float, ...] | None:
    """Compact upper-body signature for between-frame motion comparison."""

    landmark_list = list(landmarks)
    if len(landmark_list) < 13:
        return None

    nose = landmark_list[0]
    left_shoulder = landmark_list[11]
    right_shoulder = landmark_list[12]
    if not all(landmark_visible(pt) for pt in (nose, left_shoulder, right_shoulder)):
        return None

    return (
        float(nose.x),
        float(nose.y),
        float(left_shoulder.x),
        float(left_shoulder.y),
        float(right_shoulder.x),
        float(right_shoulder.y),
    )


def calculate_motion_delta(
    prev: tuple[float, ...] | None,
    curr: tuple[float, ...] | None,
) -> float:
    """Average absolute motion between two signatures (0 = still, higher = moving)."""
    if prev is None or curr is None:
        return 1.0
    return sum(abs(a - b) for a, b in zip(prev, curr)) / len(prev)
