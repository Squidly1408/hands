"""Turns 3D hand landmarks into a debounced pose.

Everything here works on MediaPipe's world landmarks (metres, origin at the hand),
so results don't depend on how far the hand is from the camera, and distances are
normalised by palm size so they don't depend on the size of the hand either.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_MCP, RING_PIP, RING_TIP = 13, 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

PALM_POINTS = (WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)

# Tip-to-wrist distance over knuckle-to-wrist distance. This holds up under hand
# rotation, unlike comparing y coordinates. Values in between are neither.
EXTENDED_RATIO = 1.15
CURLED_RATIO = 1.0


class Pose(Enum):
    MOVE = "move"
    LEFT_PINCH = "left pinch"
    RIGHT_PINCH = "right pinch"
    RING_PINCH = "ring pinch"
    PINKY_PINCH = "pinky pinch"
    SCROLL = "scroll"
    FIST = "fist"


@dataclass(frozen=True)
class HandMeasure:
    index_pinch: float
    middle_pinch: float
    ring_pinch: float
    pinky_pinch: float
    index_ratio: float
    middle_ratio: float
    ring_ratio: float
    pinky_ratio: float


def _dist(world: np.ndarray, a: int, b: int) -> float:
    return float(np.linalg.norm(world[a] - world[b]))


def measure(world: np.ndarray) -> HandMeasure:
    """Compute the scale-free quantities used for classification."""
    palm = max(_dist(world, WRIST, MIDDLE_MCP), _dist(world, INDEX_MCP, PINKY_MCP))

    def ratio(tip: int, pip: int) -> float:
        return _dist(world, tip, WRIST) / max(_dist(world, pip, WRIST), 1e-6)

    return HandMeasure(
        index_pinch=_dist(world, THUMB_TIP, INDEX_TIP) / palm,
        middle_pinch=_dist(world, THUMB_TIP, MIDDLE_TIP) / palm,
        ring_pinch=_dist(world, THUMB_TIP, RING_TIP) / palm,
        pinky_pinch=_dist(world, THUMB_TIP, PINKY_TIP) / palm,
        index_ratio=ratio(INDEX_TIP, INDEX_PIP),
        middle_ratio=ratio(MIDDLE_TIP, MIDDLE_PIP),
        ring_ratio=ratio(RING_TIP, RING_PIP),
        pinky_ratio=ratio(PINKY_TIP, PINKY_PIP),
    )


class GestureClassifier:
    """Classifies each frame, with hysteresis on pinches and debouncing on changes."""

    def __init__(self, pinch_enter: float, pinch_exit: float, stable_frames: int) -> None:
        self._pinch_enter = pinch_enter
        self._pinch_exit = pinch_exit
        self._stable_frames = stable_frames
        self.reset()

    def reset(self) -> None:
        self.pose = Pose.MOVE
        self._candidate = Pose.MOVE
        self._candidate_frames = 0

    def update(self, world: np.ndarray) -> Pose:
        raw = self._classify(measure(world))
        if raw is self.pose:
            self._candidate_frames = 0
            return self.pose
        if raw is not self._candidate:
            self._candidate = raw
            self._candidate_frames = 0
        self._candidate_frames += 1
        if self._candidate_frames >= self._stable_frames:
            self.pose = raw
            self._candidate_frames = 0
        return self.pose

    def _classify(self, m: HandMeasure) -> Pose:
        # A held pinch keeps priority: it uses the looser exit threshold, and fingers
        # curling mid-drag must not turn it into a fist.
        pinches = {
            Pose.LEFT_PINCH: m.index_pinch,
            Pose.RIGHT_PINCH: m.middle_pinch,
            Pose.RING_PINCH: m.ring_pinch,
            Pose.PINKY_PINCH: m.pinky_pinch,
        }
        if pinches.get(self.pose, self._pinch_exit) < self._pinch_exit:
            return self.pose

        # Checked before new pinches, because a fist brings the thumb close to the fingertips.
        ratios = (m.index_ratio, m.middle_ratio, m.ring_ratio, m.pinky_ratio)
        if all(r < CURLED_RATIO for r in ratios):
            return Pose.FIST

        # The raised index keeps a loosely closing hand from registering as anything
        # but the plain left pinch.
        closest = min(pinches, key=pinches.__getitem__)
        if pinches[closest] < self._pinch_enter and m.index_ratio > EXTENDED_RATIO:
            return closest
        if m.index_pinch < self._pinch_enter:
            return Pose.LEFT_PINCH

        if (
            m.index_ratio > EXTENDED_RATIO
            and m.middle_ratio > EXTENDED_RATIO
            and m.ring_ratio < EXTENDED_RATIO
            and m.pinky_ratio < EXTENDED_RATIO
        ):
            return Pose.SCROLL
        return Pose.MOVE
