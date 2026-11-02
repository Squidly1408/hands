"""Webcam capture on a background thread, so we always process the newest frame
rather than falling behind on a buffered queue of old ones."""

from __future__ import annotations

import sys
import threading
import time

import cv2
import numpy as np


class CameraError(RuntimeError):
    pass


class Camera:
    def __init__(self, index: int, width: int, height: int, timeout: float = 5.0) -> None:
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self._capture = cv2.VideoCapture(index, backend)
        if not self._capture.isOpened():
            self._capture.release()
            raise CameraError(
                f"Cannot open camera {index}. Check that no other app is using it and that "
                "camera access is allowed in Settings > Privacy & security > Camera."
            )
        self._capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._timeout = timeout
        self._condition = threading.Condition()
        self._frame: np.ndarray | None = None
        self._stopped = False
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stopped:
            ok, frame = self._capture.read()
            if ok:
                with self._condition:
                    self._frame = frame
                    self._condition.notify_all()
            else:
                time.sleep(0.01)  # A failing read returns at once; don't spin on it.

    def read(self) -> np.ndarray:
        """Block until a frame newer than the last one returned is available."""
        with self._condition:
            if not self._condition.wait_for(lambda: self._frame is not None, timeout=self._timeout):
                raise CameraError(f"No frame from the camera for {self._timeout:g}s.")
            frame, self._frame = self._frame, None
        return frame

    def close(self) -> None:
        self._stopped = True
        self._thread.join(timeout=2.0)
        self._capture.release()
