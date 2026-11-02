import numpy as np
import pytest
from handmodel import make_hand, make_pose, with_thumb_gap

from handcursor.gestures import GestureClassifier, Pose


def classifier(stable_frames=1):
    return GestureClassifier(pinch_enter=0.3, pinch_exit=0.45, stable_frames=stable_frames)


@pytest.mark.parametrize("pose", list(Pose))
def test_recognises_each_pose(pose):
    assert classifier().update(make_pose(pose)) is pose


@pytest.mark.parametrize("pose", list(Pose))
def test_independent_of_hand_size_and_rotation(pose):
    angle = np.radians(50)
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    assert classifier().update(make_pose(pose) @ rotation.T * 0.7) is pose


def test_fist_is_not_mistaken_for_a_pinch_when_thumb_is_near_the_fingers():
    world = make_hand(False, False, False, False)
    world[4] = world[8] + (0.005, 0, 0)
    assert classifier().update(world) is Pose.FIST


def test_right_pinch_needs_the_index_finger_raised():
    world = make_hand(index=False)
    world[4] = world[12] + (0.005, 0, 0)
    assert classifier().update(world) is not Pose.RIGHT_PINCH


@pytest.mark.parametrize("tip", [16, 20])
def test_action_pinches_need_the_index_finger_raised(tip):
    world = make_hand(index=False)
    world[4] = world[tip] + (0.005, 0, 0)
    assert classifier().update(world) not in (Pose.RING_PINCH, Pose.PINKY_PINCH)


def test_pointing_finger_alone_moves():
    assert classifier().update(make_hand(True, False, False, False)) is Pose.MOVE


def test_pinch_hysteresis():
    c = classifier()
    assert c.update(with_thumb_gap(0.35)) is Pose.MOVE  # Not close enough to start.
    assert c.update(with_thumb_gap(0.2)) is Pose.LEFT_PINCH
    assert c.update(with_thumb_gap(0.35)) is Pose.LEFT_PINCH  # Not far enough to end.
    assert c.update(with_thumb_gap(0.5)) is Pose.MOVE


def test_held_pinch_survives_fingers_curling():
    c = classifier()
    c.update(make_pose(Pose.LEFT_PINCH))
    world = make_hand(False, False, False, False)
    world[4] = world[8] + (0.005, 0, 0)
    assert c.update(world) is Pose.LEFT_PINCH


def test_single_frame_blip_is_debounced():
    c = classifier(stable_frames=2)
    assert c.update(make_pose(Pose.LEFT_PINCH)) is Pose.MOVE
    assert c.update(make_pose(Pose.MOVE)) is Pose.MOVE
    assert c.update(make_pose(Pose.LEFT_PINCH)) is Pose.MOVE
    assert c.update(make_pose(Pose.LEFT_PINCH)) is Pose.LEFT_PINCH


def test_debounce_requires_the_same_candidate_consecutively():
    c = classifier(stable_frames=2)
    c.update(make_pose(Pose.LEFT_PINCH))
    assert c.update(make_pose(Pose.FIST)) is Pose.MOVE
    assert c.update(make_pose(Pose.FIST)) is Pose.FIST
