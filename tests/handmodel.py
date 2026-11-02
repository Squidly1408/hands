"""Builds synthetic world landmarks for hands in known poses, palm up the y axis."""

from __future__ import annotations

import numpy as np

from handcursor.gestures import Pose

_FINGER_BASES = {"index": (5, -0.03), "middle": (9, -0.01), "ring": (13, 0.01), "pinky": (17, 0.03)}


def make_hand(index=True, middle=True, ring=True, pinky=True) -> np.ndarray:
    """A hand with the given fingers extended and the rest curled, thumb out to the side."""
    world = np.zeros((21, 3))
    world[1:5] = [(-0.03, 0.02, 0), (-0.05, 0.045, 0), (-0.065, 0.07, 0), (-0.075, 0.09, 0)]
    states = {"index": index, "middle": middle, "ring": ring, "pinky": pinky}
    for name, (base, x) in _FINGER_BASES.items():
        if states[name]:
            joints = [(x, 0.09, 0), (x, 0.125, 0), (x, 0.15, 0), (x, 0.17, 0)]
        else:
            joints = [(x, 0.09, 0), (x, 0.12, 0), (x, 0.10, 0.02), (x, 0.075, 0.025)]
        world[base : base + 4] = joints
    return world


def make_pose(pose: Pose) -> np.ndarray:
    if pose is Pose.MOVE:
        return make_hand()
    if pose is Pose.SCROLL:
        return make_hand(ring=False, pinky=False)
    if pose is Pose.FIST:
        return make_hand(False, False, False, False)
    world = make_hand()
    tip = {Pose.LEFT_PINCH: 8, Pose.RIGHT_PINCH: 12, Pose.RING_PINCH: 16, Pose.PINKY_PINCH: 20}[pose]
    world[4] = world[tip] + (0.005, 0, 0)
    return world


def with_thumb_gap(palm_fraction: float) -> np.ndarray:
    """An open hand with the thumb this far from the index tip, as a fraction of palm size."""
    world = make_hand()
    world[4] = world[8] + (-0.09 * palm_fraction, 0, 0)
    return world
