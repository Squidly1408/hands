"""MediaPipe hand tracking, and the model file it needs."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from handcursor.control import HandFrame
from handcursor.gestures import PALM_POINTS

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_PATH = Path.home() / ".cache" / "handcursor" / "hand_landmarker.task"


class ModelDownloadError(RuntimeError):
    pass


def ensure_model(path: Path = MODEL_PATH) -> Path:
    """Download the model on first run. The rename means an interrupted download
    can't leave a partial file that later runs would mistake for the model."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    print(f"Downloading the hand tracking model to {path} ...")
    try:
        urllib.request.urlretrieve(MODEL_URL, partial)
    except (urllib.error.URLError, OSError) as e:
        partial.unlink(missing_ok=True)
        raise ModelDownloadError(f"Could not download the model from {MODEL_URL}: {e}") from e
    os.replace(partial, path)
    return path


@dataclass(frozen=True)
class TrackedHand:
    frame: HandFrame
    image_points: np.ndarray  # 21x2 landmarks in the image, 0-1, for drawing.


class HandTracker:
    def __init__(self, hand: str, model_path: Path) -> None:
        self._hand = hand
        self._last_timestamp = -1
        self._landmarker = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)),
                running_mode=vision.RunningMode.VIDEO,
                # Even when using one hand, seeing both is how we pick out the right one.
                num_hands=2,
            )
        )

    def detect(self, bgr: np.ndarray, now: float) -> list[TrackedHand]:
        """Find the hands in a mirrored frame, at most one per label. MediaPipe's
        left/right labels assume mirrored input, so they come out as the user's own."""
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        # Video mode rejects timestamps that don't strictly increase.
        timestamp = max(int(now * 1000), self._last_timestamp + 1)
        self._last_timestamp = timestamp
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp)

        hands: dict[str, TrackedHand] = {}
        for i, handedness in enumerate(result.handedness):
            label = handedness[0].category_name.lower()
            if label in hands or self._hand not in ("both", label):
                continue
            points = np.array([(p.x, p.y) for p in result.hand_landmarks[i]])
            world = np.array([(p.x, p.y, p.z) for p in result.hand_world_landmarks[i]])
            # The palm barely moves when fingers do, so unlike a fingertip it
            # stays put through a pinch.
            palm = points[list(PALM_POINTS)].mean(axis=0)
            hands[label] = TrackedHand(HandFrame((float(palm[0]), float(palm[1])), world, label), points)
        return list(hands.values())

    def close(self) -> None:
        self._landmarker.close()
