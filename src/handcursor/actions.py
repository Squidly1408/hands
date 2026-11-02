"""What the action gestures do: open things, send shortcuts, show the launcher.

An action is written as text so it can live in the config file:
    open:TARGET   an app, file, folder or URL, anything the Run dialog would accept
    keys:COMBO    a keyboard shortcut in pynput's format, such as <cmd>+d
    launcher      toggle the app launcher
    none          do nothing
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Protocol

from handcursor.config import Config, ConfigError
from handcursor.gestures import Pose


@dataclass(frozen=True)
class Action:
    kind: str
    value: str = ""


def parse_action(text: str) -> Action:
    if text in ("launcher", "none"):
        return Action(text)
    kind, _, value = text.partition(":")
    if kind not in ("open", "keys") or not value:
        raise ConfigError(f"Action must be open:TARGET, keys:COMBO, launcher or none, not {text!r}")
    if kind == "keys":
        from pynput.keyboard import HotKey

        try:
            HotKey.parse(value)
        except ValueError as e:
            raise ConfigError(f"Invalid key combination in action {text!r}: {e}") from e
    return Action(kind, value)


def open_target(target: str) -> None:
    os.startfile(target)


def send_keys(combo: str) -> None:
    from pynput.keyboard import Controller, HotKey

    keyboard = Controller()
    keys = HotKey.parse(combo)
    pressed = []
    try:
        for key in keys:
            keyboard.press(key)
            pressed.append(key)
    finally:
        # Whatever happens, never leave a modifier stuck down.
        for key in reversed(pressed):
            keyboard.release(key)


def perform(action: Action) -> None:
    """Run an open or keys action. A bad target is reported, not fatal: it shouldn't
    take down cursor control, or come as a surprise from the launcher's own process."""
    try:
        if action.kind == "open":
            open_target(action.value)
        elif action.kind == "keys":
            send_keys(action.value)
    except OSError as e:
        print(f"Could not {action.kind} {action.value!r}: {e}")


class Actions(Protocol):
    def run(self, pose: Pose) -> None: ...
    def close(self) -> None: ...


class SystemActions:
    def __init__(self, config: Config) -> None:
        self._bindings = {
            Pose.RING_PINCH: parse_action(config.ring_pinch_action),
            Pose.PINKY_PINCH: parse_action(config.pinky_pinch_action),
        }
        for _, action in config.apps:
            parse_action(action)
        self._apps = config.apps
        self._launcher: subprocess.Popen | None = None

    def run(self, pose: Pose) -> None:
        action = self._bindings[pose]
        if action.kind == "launcher":
            self._toggle_launcher()
        elif action.kind != "none":
            self._perform(action)

    def close(self) -> None:
        if self._launcher_open():
            self._launcher.terminate()

    def _perform(self, action: Action) -> None:
        perform(action)

    def _launcher_open(self) -> bool:
        return self._launcher is not None and self._launcher.poll() is None

    def _toggle_launcher(self) -> None:
        # In its own process because Tk wants the main thread, and the camera loop has that.
        if self._launcher_open():
            self._launcher.terminate()
        else:
            self._launcher = subprocess.Popen([sys.executable, "-m", "handcursor.launcher", json.dumps(self._apps)])


class DryRunActions(SystemActions):
    """Prints actions rather than performing them."""

    def _perform(self, action: Action) -> None:
        print(f"[dry run] {action.kind} {action.value}")

    def _toggle_launcher(self) -> None:
        print("[dry run] toggle launcher")
