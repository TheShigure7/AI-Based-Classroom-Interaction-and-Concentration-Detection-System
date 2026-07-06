"""Minimal camera capture service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import cv2
import numpy as np


@dataclass
class CameraConfig:
    """Basic camera configuration."""

    source: int | str = 0
    width: int = 1280
    height: int = 720


class CameraService:
    """Wraps OpenCV camera access for local preview and future API use."""

    def __init__(self, config: Optional[CameraConfig] = None) -> None:
        self.config = config or CameraConfig()
        self._capture: Optional[cv2.VideoCapture] = None

    def open(self) -> None:
        """Open the configured camera."""
        if self._capture is not None and self._capture.isOpened():
            return

        self._preflight_source()
        capture = cv2.VideoCapture(self.config.source)
        if isinstance(self.config.source, int):
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        elif hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not capture.isOpened():
            raise RuntimeError(
                f"Unable to open camera source: {self.config.source}. "
                "Check whether the camera or stream is available."
            )

        self._capture = capture

    def read_frame(self) -> np.ndarray:
        """Read one frame from the camera."""
        if self._capture is None or not self._capture.isOpened():
            self.open()

        assert self._capture is not None
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read frame from camera.")

        return frame

    def release(self) -> None:
        """Release camera resources."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def preview(self, window_name: str = "Classroom Camera Preview") -> None:
        """Show a local OpenCV preview window until the user presses q."""
        self.open()

        try:
            while True:
                frame = self.read_frame()
                cv2.imshow(window_name, frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
        finally:
            self.release()
            cv2.destroyAllWindows()

    def _preflight_source(self) -> None:
        """Fail faster for unreachable HTTP video streams."""
        if not isinstance(self.config.source, str):
            return

        parsed = urlparse(self.config.source)
        if parsed.scheme not in {"http", "https"}:
            return

        request = Request(self.config.source, headers={"User-Agent": "ClassroomMonitor/1.0"})
        try:
            with urlopen(request, timeout=3) as response:
                status_code = getattr(response, "status", 200)
                if status_code >= 400:
                    raise RuntimeError(
                        f"Unable to open camera source: {self.config.source}. "
                        f"HTTP status {status_code}."
                    )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Unable to open camera source: {self.config.source}. "
                "Check whether the camera or stream is available."
            ) from exc
