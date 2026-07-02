"""Phone distraction analysis helpers."""

from __future__ import annotations

from app.services.analysis.behavior_rules import is_phone_risk


class PhoneUseAnalyzer:
    """Analyze whether a detected phone likely indicates distraction."""

    def is_phone_risk(
        self,
        person_bbox: tuple[int, int, int, int],
        phone_bbox: tuple[int, int, int, int],
        head_down: bool,
    ) -> bool:
        """Return whether the phone detection is likely associated with the student."""
        return is_phone_risk(person_bbox, phone_bbox, head_down)
