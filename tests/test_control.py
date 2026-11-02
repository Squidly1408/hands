import pytest
from handmodel import make_pose

from handcursor.config import Config
from handcursor.control import Controller, HandFrame
from handcursor.gestures import Pose
from handcursor.screen import Rect, Workspace

FRAME = 1 / 30
SCREEN = Workspace([Rect(0, 0, 1001, 1001)])
CENTRE = (0.5, 0.5)


class FakeActions:
    def __init__(self):
        self.ran = []

    def run(self, pose):
        self.ran.append(pose)

    def close(self):
        pass


class FakeMouse:
    def __init__(self):
        self.position = None
        self.events = []

    def move(self, x, y):
        self.position = (x, y)

    def press(self, button):
        self.events.append(("press", button))

    def release(self, button):
        self.events.append(("release", button))

    def click(self, button):
        self.events.append(("click", button))

    def scroll(self, notches):
        self.events.append(("scroll", notches))


class Rig:
    def __init__(self, workspace=SCREEN, **config):
        self.mouse = FakeMouse()
        self.actions = FakeActions()
        settings = {"region": (0.0, 0.0, 1.0, 1.0), "stable_frames": 1, **config}
        self.controller = Controller(Config(**settings), self.mouse, self.actions, workspace)
        self.now = 0.0

    def hold(self, pose, seconds=FRAME, palm=CENTRE):
        self.hold_hands({"right": (pose, palm)}, seconds)

    def hold_hands(self, hands, seconds=FRAME):
        """Advance with the given hands visible: {label: (pose, palm)}."""
        frames = [HandFrame(palm, make_pose(pose), label) for label, (pose, palm) in hands.items()]
        for _ in range(max(1, round(seconds / FRAME))):
            self.now += FRAME
            self.controller.update(frames, self.now)

    def lose_hand(self, seconds):
        self.hold_hands({}, seconds)


def test_open_hand_moves_the_cursor():
    rig = Rig()
    rig.hold(Pose.MOVE, palm=(0.25, 0.75))
    assert rig.mouse.position == (250, 750)


def test_region_maps_to_the_whole_screen_and_clamps():
    rig = Rig(region=(0.2, 0.2, 0.8, 0.8))
    rig.hold(Pose.MOVE, palm=(0.2, 0.8))
    assert rig.mouse.position == (0, 1000)
    rig = Rig(region=(0.2, 0.2, 0.8, 0.8))
    rig.hold(Pose.MOVE, palm=(0.95, 0.05))
    assert rig.mouse.position == (1000, 0)


def test_screen_offset_is_applied():
    rig = Rig(workspace=Workspace([Rect(-500, 100, 1001, 1001)]))
    rig.hold(Pose.MOVE, palm=(0.0, 0.0))
    assert rig.mouse.position == (-500, 100)


# Laptop below two external monitors, the layout that showed up the dead zone bug,
# with the second external turned to portrait.
LAYOUT = Workspace([Rect(0, 0, 1920, 1080), Rect(954, -1085, 1920, 1080), Rect(-966, -1920, 1080, 1920)])


def test_cursor_crosses_every_monitor():
    rig = Rig(workspace=LAYOUT)
    rig.hold(Pose.MOVE, palm=(0.4, 0.9))
    assert rig.mouse.position[1] > 0  # On the laptop.
    rig = Rig(workspace=LAYOUT)
    rig.hold(Pose.MOVE, palm=(0.9, 0.3))
    assert rig.mouse.position[0] > 1920 and rig.mouse.position[1] < 0  # On the landscape external.
    rig = Rig(workspace=LAYOUT)
    rig.hold(Pose.MOVE, palm=(0.05, 0.1))
    assert rig.mouse.position[0] < 114 and rig.mouse.position[1] < 0  # On the portrait external.


@pytest.mark.parametrize("x", [i / 20 for i in range(21)])
@pytest.mark.parametrize("y", [i / 20 for i in range(21)])
def test_cursor_never_lands_in_a_dead_zone(x, y):
    rig = Rig(workspace=LAYOUT)
    rig.hold(Pose.MOVE, palm=(x, y))
    px, py = rig.mouse.position
    assert any(m.clamp(px, py) == (px, py) for m in LAYOUT.monitors)


def test_portrait_monitor_maps_its_full_height():
    rig = Rig(workspace=Workspace([Rect(0, 0, 1080, 1920)]))
    rig.hold(Pose.MOVE, palm=(1.0, 1.0))
    assert rig.mouse.position == (1079, 1919)


def test_action_gesture_needs_holding_and_fires_once():
    rig = Rig(action_hold=0.5)
    rig.hold(Pose.RING_PINCH, 0.3)
    assert rig.actions.ran == []
    rig.hold(Pose.RING_PINCH, 2.0)
    assert rig.actions.ran == [Pose.RING_PINCH]
    assert rig.mouse.events == []


def test_action_gesture_released_early_does_nothing():
    rig = Rig(action_hold=0.5)
    rig.hold(Pose.PINKY_PINCH, 0.3)
    rig.hold(Pose.MOVE)
    rig.hold(Pose.PINKY_PINCH, 0.3)
    rig.hold(Pose.MOVE)
    assert rig.actions.ran == []


def test_action_gesture_can_fire_again_after_release():
    rig = Rig(action_hold=0.1)
    rig.hold(Pose.PINKY_PINCH, 0.2)
    rig.hold(Pose.MOVE)
    rig.hold(Pose.PINKY_PINCH, 0.2)
    assert rig.actions.ran == [Pose.PINKY_PINCH, Pose.PINKY_PINCH]


def test_other_hand_can_fire_an_action_while_steering_continues():
    rig = Rig(action_hold=0.1)
    rig.hold_hands({"left": (Pose.RING_PINCH, (0.2, 0.5)), "right": (Pose.MOVE, (0.8, 0.5))}, 0.2)
    assert rig.actions.ran == [Pose.RING_PINCH]
    assert rig.mouse.position == (800, 500)


def test_steering_hand_holds_the_cursor_during_an_action_gesture():
    rig = Rig()
    rig.hold(Pose.MOVE, palm=(0.5, 0.5))
    position = rig.mouse.position
    rig.hold(Pose.RING_PINCH, 0.2, palm=(0.9, 0.9))
    assert rig.mouse.position == position


def test_switching_monitor_jumps_straight_there_without_gliding():
    rig = Rig()
    rig.hold(Pose.MOVE, palm=(0.0, 0.0))
    rig.controller.set_workspace(Workspace([Rect(5000, 0, 1001, 1001)]))
    rig.hold(Pose.MOVE, palm=(0.0, 0.0))
    assert rig.mouse.position == (5000, 0)


def test_quick_pinch_clicks_on_release():
    rig = Rig()
    rig.hold(Pose.MOVE)
    rig.hold(Pose.LEFT_PINCH, 0.1)
    assert rig.mouse.events == []
    rig.hold(Pose.MOVE)
    assert rig.mouse.events == [("click", "left")]


def test_cursor_stays_put_during_a_quick_pinch():
    rig = Rig()
    rig.hold(Pose.MOVE, palm=(0.5, 0.5))
    position = rig.mouse.position
    rig.hold(Pose.LEFT_PINCH, 0.1, palm=(0.6, 0.6))
    assert rig.mouse.position == position


def test_long_pinch_drags_and_releases():
    rig = Rig(drag_hold=0.2)
    rig.hold(Pose.MOVE, palm=(0.5, 0.5))
    start = rig.mouse.position
    rig.hold(Pose.LEFT_PINCH, 0.3, palm=(0.8, 0.5))
    assert rig.mouse.events == [("press", "left")]
    assert rig.mouse.position != start
    rig.hold(Pose.MOVE)
    assert rig.mouse.events == [("press", "left"), ("release", "left")]


def test_right_pinch_clicks_once_however_long_it_is_held():
    rig = Rig()
    rig.hold(Pose.RIGHT_PINCH, 1.0)
    rig.hold(Pose.MOVE)
    assert rig.mouse.events == [("click", "right")]


def test_scroll_follows_vertical_movement_and_freezes_the_cursor():
    rig = Rig(scroll_speed=10.0)
    rig.hold(Pose.MOVE, palm=(0.5, 0.5))
    position = rig.mouse.position
    rig.hold(Pose.SCROLL, palm=(0.5, 0.5))
    rig.hold(Pose.SCROLL, palm=(0.5, 0.3))
    assert rig.mouse.events == [("scroll", 2)]
    rig.hold(Pose.SCROLL, palm=(0.5, 0.5))
    assert rig.mouse.events == [("scroll", 2), ("scroll", -2)]
    assert rig.mouse.position == position


def test_slow_scroll_accumulates():
    rig = Rig(scroll_speed=10.0)
    rig.hold(Pose.SCROLL, palm=(0.5, 0.5))
    for y in (0.47, 0.44, 0.41, 0.38):  # Each step alone is under one notch.
        rig.hold(Pose.SCROLL, palm=(0.5, y))
    assert rig.mouse.events == [("scroll", 1)]


def test_fist_pauses_the_cursor():
    rig = Rig()
    rig.hold(Pose.MOVE, palm=(0.5, 0.5))
    position = rig.mouse.position
    rig.hold(Pose.FIST, 0.5, palm=(0.9, 0.9))
    assert rig.mouse.position == position
    assert rig.mouse.events == []


def test_tracking_flicker_keeps_a_drag_alive():
    rig = Rig(drag_hold=0.0, hand_lost_grace=0.25)
    rig.hold(Pose.LEFT_PINCH, 0.1)
    rig.lose_hand(0.1)
    assert rig.controller.dragging
    assert rig.mouse.events == [("press", "left")]


def test_losing_the_hand_releases_a_drag():
    rig = Rig(drag_hold=0.0, hand_lost_grace=0.25)
    rig.hold(Pose.LEFT_PINCH, 0.1)
    rig.lose_hand(0.5)
    assert not rig.controller.dragging
    assert rig.mouse.events == [("press", "left"), ("release", "left")]


def test_losing_the_hand_mid_pinch_does_not_click_on_return():
    rig = Rig(stable_frames=2)
    rig.hold(Pose.LEFT_PINCH, 0.1)
    rig.lose_hand(0.5)
    rig.hold(Pose.MOVE, 0.2)
    assert rig.mouse.events == []


@pytest.mark.parametrize("leave", ["set_enabled", "shutdown"])
def test_pausing_or_quitting_releases_a_drag(leave):
    rig = Rig(drag_hold=0.0)
    rig.hold(Pose.LEFT_PINCH, 0.1)
    if leave == "shutdown":
        rig.controller.shutdown()
    else:
        rig.controller.set_enabled(False)
    assert rig.mouse.events == [("press", "left"), ("release", "left")]


LEFT_SIDE = (0.2, 0.5)
RIGHT_SIDE = (0.8, 0.5)


def test_cursor_hand_steers_when_both_are_visible():
    rig = Rig()
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)})
    assert rig.mouse.position == (800, 500)
    assert rig.controller.steering == "right"


def test_cursor_hand_setting_chooses_the_steering_hand():
    rig = Rig(cursor_hand="left")
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)})
    assert rig.mouse.position == (200, 500)


def test_either_hand_steers_alone_and_steering_returns_without_gliding():
    rig = Rig()
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE)})
    assert rig.mouse.position == (200, 500)
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)})
    assert rig.mouse.position == (800, 500)


def test_steering_passes_over_only_after_the_grace_period():
    rig = Rig(hand_lost_grace=0.25)
    both = {"left": (Pose.MOVE, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)}
    rig.hold_hands(both)
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE)}, 0.1)
    assert rig.controller.steering == "right"
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE)}, 0.3)
    assert rig.controller.steering == "left"
    assert rig.mouse.position == (200, 500)


def test_other_hand_clicks_while_the_cursor_keeps_moving():
    rig = Rig()
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)})
    rig.hold_hands({"left": (Pose.LEFT_PINCH, LEFT_SIDE), "right": (Pose.MOVE, (0.9, 0.5))}, 0.1)
    assert rig.mouse.position[0] > 800
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE), "right": (Pose.MOVE, (0.9, 0.5))})
    assert rig.mouse.events == [("click", "left")]


def test_other_hand_holds_a_drag_while_the_steering_hand_moves():
    rig = Rig(drag_hold=0.0)
    rig.hold_hands({"left": (Pose.LEFT_PINCH, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)}, 0.1)
    assert rig.controller.dragging
    assert rig.mouse.position == (800, 500)
    assert rig.mouse.events == [("press", "left")]


def test_other_hand_right_clicks_and_scrolls():
    rig = Rig(scroll_speed=10.0)
    rig.hold_hands({"left": (Pose.RIGHT_PINCH, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)}, 0.1)
    assert rig.mouse.events == [("click", "right")]
    rig.hold_hands({"left": (Pose.SCROLL, (0.2, 0.5)), "right": (Pose.MOVE, RIGHT_SIDE)})
    rig.hold_hands({"left": (Pose.SCROLL, (0.2, 0.3)), "right": (Pose.MOVE, (0.9, 0.5))}, 0.1)
    assert rig.mouse.events[-1] == ("scroll", 2)
    assert rig.mouse.position[0] > 800


def test_fist_on_the_other_hand_does_not_pause_the_cursor():
    rig = Rig()
    rig.hold_hands({"left": (Pose.FIST, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)})
    assert rig.mouse.position == (800, 500)


def test_two_hands_dragging_share_one_button():
    rig = Rig(drag_hold=0.0)
    rig.hold_hands({"left": (Pose.LEFT_PINCH, LEFT_SIDE), "right": (Pose.LEFT_PINCH, RIGHT_SIDE)}, 0.1)
    assert rig.mouse.events == [("press", "left")]
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE), "right": (Pose.LEFT_PINCH, RIGHT_SIDE)})
    assert rig.mouse.events == [("press", "left")]
    rig.hold_hands({"left": (Pose.MOVE, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)})
    assert rig.mouse.events == [("press", "left"), ("release", "left")]


def test_quick_pinch_during_the_other_hands_drag_does_not_break_it():
    rig = Rig(drag_hold=0.3)
    rig.hold_hands({"left": (Pose.LEFT_PINCH, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)}, 0.4)
    rig.hold_hands({"left": (Pose.LEFT_PINCH, LEFT_SIDE), "right": (Pose.LEFT_PINCH, RIGHT_SIDE)}, 0.1)
    rig.hold_hands({"left": (Pose.LEFT_PINCH, LEFT_SIDE), "right": (Pose.MOVE, RIGHT_SIDE)})
    assert rig.mouse.events == [("press", "left")]


def test_losing_a_dragging_hand_keeps_the_button_for_the_other():
    rig = Rig(drag_hold=0.0, hand_lost_grace=0.25)
    rig.hold_hands({"left": (Pose.LEFT_PINCH, LEFT_SIDE), "right": (Pose.LEFT_PINCH, RIGHT_SIDE)}, 0.1)
    rig.hold_hands({"right": (Pose.LEFT_PINCH, RIGHT_SIDE)}, 0.5)
    assert rig.mouse.events == [("press", "left")]
    rig.lose_hand(0.5)
    assert rig.mouse.events == [("press", "left"), ("release", "left")]


def test_paused_controller_does_nothing():
    rig = Rig()
    rig.controller.set_enabled(False)
    rig.hold(Pose.MOVE)
    rig.hold(Pose.RIGHT_PINCH)
    assert rig.mouse.position is None
    assert rig.mouse.events == []
