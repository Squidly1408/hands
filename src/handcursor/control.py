"""The state machine that turns tracked hand frames into mouse actions.

Each hand has its own gesture state, and either can click, drag or scroll. One of them
steers the cursor, since there is only one. Timing comes in through `now`, so all of
this runs under test without a camera.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from handcursor.actions import Actions
from handcursor.config import Config
from handcursor.gestures import GestureClassifier, Pose
from handcursor.mouse import Mouse
from handcursor.screen import Workspace
from handcursor.smoothing import OneEuroFilter

ACTION_POSES = (Pose.RING_PINCH, Pose.PINKY_PINCH)


@dataclass(frozen=True)
class HandFrame:
    palm: tuple[float, float]  # Palm centre in the mirrored camera image, 0-1.
    world: np.ndarray  # 21x3 world landmarks.
    label: str  # "left" or "right".


class _HandState:
    def __init__(self, config: Config, now: float) -> None:
        self.classifier = GestureClassifier(config.pinch_enter, config.pinch_exit, config.stable_frames)
        self.pose = Pose.MOVE
        self.last_seen = now
        self.pinch_started = 0.0
        self.scroll_anchor = 0.0
        self.dragging = False
        self.action_fired = False


class Controller:
    def __init__(self, config: Config, mouse: Mouse, actions: Actions, workspace: Workspace) -> None:
        self._config = config
        self._mouse = mouse
        self._actions = actions
        self._workspace = workspace
        self._filter_x = OneEuroFilter(config.min_cutoff, config.beta)
        self._filter_y = OneEuroFilter(config.min_cutoff, config.beta)
        self._hands: dict[str, _HandState] = {}
        self._last_position: tuple[int, int] | None = None
        self.enabled = True
        self.steering: str | None = None

    @property
    def dragging(self) -> bool:
        return any(state.dragging for state in self._hands.values())

    @property
    def poses(self) -> dict[str, Pose]:
        return {label: state.pose for label, state in sorted(self._hands.items())}

    def update(self, hands: Sequence[HandFrame], now: float) -> None:
        """Advance by one camera frame. `hands` holds at most one hand per label."""
        if not self.enabled:
            return
        seen = {hand.label: hand for hand in hands}

        # Tracking flickers, so don't drop a drag or forget a pinch over a frame or two.
        for label, state in list(self._hands.items()):
            if label not in seen and now - state.last_seen > self._config.hand_lost_grace:
                self._forget(label)

        for label, hand in seen.items():
            state = self._hands.setdefault(label, _HandState(self._config, now))
            state.last_seen = now
            self._update_gestures(state, hand, now)

        self._choose_steering()
        if self.steering in seen:
            self._steer(seen[self.steering], now)

    def set_enabled(self, enabled: bool) -> None:
        if not enabled:
            self._reset()
        self.enabled = enabled

    def set_workspace(self, workspace: Workspace) -> None:
        self._reset()
        self._workspace = workspace

    def shutdown(self) -> None:
        """Never leave the button held down after exiting."""
        self._reset()

    def _update_gestures(self, state: _HandState, hand: HandFrame, now: float) -> None:
        pose = state.classifier.update(hand.world)
        if pose is not state.pose:
            self._leave(state)
            self._enter(pose, state, hand, now)
            state.pose = pose

        if state.pose is Pose.LEFT_PINCH and not state.dragging and now - state.pinch_started >= self._config.drag_hold:
            self._start_drag(state)
        elif state.pose is Pose.SCROLL:
            self._scroll(state, hand)
        elif (
            state.pose in ACTION_POSES
            and not state.action_fired
            and now - state.pinch_started >= self._config.action_hold
        ):
            # Once per gesture, however long it's held.
            self._actions.run(state.pose)
            state.action_fired = True

    def _enter(self, pose: Pose, state: _HandState, hand: HandFrame, now: float) -> None:
        if pose is Pose.LEFT_PINCH or pose in ACTION_POSES:
            state.pinch_started = now
            state.action_fired = False
        elif pose is Pose.RIGHT_PINCH:
            self._mouse.click("right")
        elif pose is Pose.SCROLL:
            state.scroll_anchor = hand.palm[1]

    def _leave(self, state: _HandState) -> None:
        if state.pose is not Pose.LEFT_PINCH:
            return
        if state.dragging:
            self._end_drag(state)
        elif not self.dragging:
            # A click would let go of the button the other hand is dragging with.
            self._mouse.click("left")

    def _start_drag(self, state: _HandState) -> None:
        if not self.dragging:
            self._mouse.press("left")
        state.dragging = True

    def _end_drag(self, state: _HandState) -> None:
        state.dragging = False
        if not self.dragging:
            self._mouse.release("left")

    def _scroll(self, state: _HandState, hand: HandFrame) -> None:
        # Hand up (smaller y) scrolls up. The anchor advances only by whole notches
        # sent, so slow movement accumulates rather than being lost to rounding.
        y = hand.palm[1]
        notches = int((state.scroll_anchor - y) * self._config.scroll_speed)
        if notches:
            self._mouse.scroll(notches)
            state.scroll_anchor -= notches / self._config.scroll_speed

    def _choose_steering(self) -> None:
        if self._config.cursor_hand in self._hands:
            steering = self._config.cursor_hand
        else:
            steering = next(iter(self._hands), None)
        if steering != self.steering:
            # The hands are in different places, so go straight there rather than glide.
            self._filter_x.reset()
            self._filter_y.reset()
            self.steering = steering

    def _steer(self, hand: HandFrame, now: float) -> None:
        # The filter keeps running while the cursor is held still, so it isn't stale on resume.
        x, y = self._to_screen(hand.palm)
        x = self._filter_x.update(x, now)
        y = self._filter_y.update(y, now)

        # Holding the cursor during a pinch means a click lands where you aimed,
        # not wherever the fingers closing nudged the hand to.
        state = self._hands[hand.label]
        if state.pose is Pose.MOVE or state.dragging:
            self._move(round(x), round(y))

    def _move(self, x: int, y: int) -> None:
        x, y = self._workspace.snap(x, y)
        if (x, y) != self._last_position:
            self._mouse.move(x, y)
            self._last_position = (x, y)

    def _to_screen(self, palm: tuple[float, float]) -> tuple[float, float]:
        left, top, right, bottom = self._config.region
        u = min(max((palm[0] - left) / (right - left), 0.0), 1.0)
        v = min(max((palm[1] - top) / (bottom - top), 0.0), 1.0)
        bounds = self._workspace.bounds
        return bounds.left + u * (bounds.width - 1), bounds.top + v * (bounds.height - 1)

    def _forget(self, label: str) -> None:
        state = self._hands[label]
        if state.dragging:
            self._end_drag(state)
        del self._hands[label]

    def _reset(self) -> None:
        for label in list(self._hands):
            self._forget(label)
        self.steering = None
        self._filter_x.reset()
        self._filter_y.reset()
        self._last_position = None
