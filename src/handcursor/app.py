"""Command line entry point and the main capture-track-control loop."""

from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path

import cv2

from handcursor import preview
from handcursor.actions import Actions, DryRunActions, SystemActions
from handcursor.camera import Camera, CameraError
from handcursor.config import Config, ConfigError, load_config
from handcursor.control import Controller
from handcursor.mouse import DryRunMouse, Mouse, SystemMouse
from handcursor.screen import ScreenSelection, enable_dpi_awareness, list_monitors
from handcursor.tracker import HandTracker, ModelDownloadError, ensure_model

KEY_ESC = 27
MONITOR_REFRESH_SECONDS = 2.0
CAMERA_ROTATIONS = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def _monitor_arg(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="handcursor", description="Control the cursor with your hands.")
    parser.add_argument("--config", type=Path, help="TOML settings file (see config.example.toml)")
    parser.add_argument("--camera", type=int, help="camera index (default 0)")
    parser.add_argument("--camera-rotation", type=int, help="degrees the webcam is turned: 0, 90, 180 or 270")
    parser.add_argument("--monitor", type=_monitor_arg, help="all (default), or a monitor number where 0 is the primary")
    parser.add_argument("--hand", choices=("both", "left", "right"), help="which hands to use (default both)")
    parser.add_argument("--cursor-hand", choices=("left", "right"), help="hand that steers when both are visible")
    parser.add_argument("--dry-run", action="store_true", help="track and print actions without performing them")
    parser.add_argument("--no-preview", action="store_true", help="run without the camera preview window")
    parser.add_argument("--fullscreen", action="store_true", default=None, help="start with the preview fullscreen")
    parser.add_argument("--list-monitors", action="store_true", help="print the monitors and exit")
    return parser.parse_args(argv)


def run(config: Config, mouse: Mouse, actions: Actions, show_preview: bool) -> None:
    screens = ScreenSelection(config.monitor)
    controller = Controller(config, mouse, actions, screens.workspace)
    tracker = HandTracker(config.hand, ensure_model())
    camera = Camera(config.camera_index, config.camera_width, config.camera_height)
    rotation = CAMERA_ROTATIONS.get(config.camera_rotation)

    # Global hotkeys arrive on pynput's thread; the main loop picks them up.
    toggle_requested = threading.Event()
    quit_requested = threading.Event()
    monitor_requested = threading.Event()
    from pynput.keyboard import GlobalHotKeys

    hotkeys = GlobalHotKeys(
        {
            config.toggle_hotkey: toggle_requested.set,
            config.quit_hotkey: quit_requested.set,
            config.monitor_hotkey: monitor_requested.set,
        }
    )
    hotkeys.start()

    print(f"Controlling {screens.label}.")
    print(f"Pause/resume: {config.toggle_hotkey}   Next screen: {config.monitor_hotkey}   Quit: {config.quit_hotkey}")

    fps = 0.0
    last_frame = time.monotonic()
    last_refresh = last_frame
    try:
        if show_preview:
            preview.open_window(config.fullscreen)
        while not quit_requested.is_set():
            frame = camera.read()
            if rotation is not None:
                frame = cv2.rotate(frame, rotation)
            frame = cv2.flip(frame, 1)
            now = time.monotonic()
            hands = tracker.detect(frame, now)

            if toggle_requested.is_set():
                toggle_requested.clear()
                controller.set_enabled(not controller.enabled)
            if monitor_requested.is_set():
                monitor_requested.clear()
                screens.next()
                controller.set_workspace(screens.workspace)
            if now - last_refresh >= MONITOR_REFRESH_SECONDS:
                last_refresh = now
                if screens.refresh():
                    print(f"Screen layout changed. Controlling {screens.label}.")
                    controller.set_workspace(screens.workspace)
            controller.update([hand.frame for hand in hands], now)

            if show_preview:
                fps += 0.1 * (1.0 / max(now - last_frame, 1e-3) - fps)
                last_frame = now
                status = _status(controller, screens.label, fps)
                preview.draw(frame, hands, controller.steering, config.region, status, controller.enabled)
                key = preview.show(frame)
                # A fullscreen window has no title bar, and Esc is the usual way out of one.
                if key == KEY_ESC and preview.is_fullscreen():
                    preview.set_fullscreen(False)
                elif key in (ord("q"), KEY_ESC) or preview.window_closed():
                    break
                elif key == ord("f"):
                    preview.set_fullscreen(not preview.is_fullscreen())
                elif key == ord(" "):
                    toggle_requested.set()
                elif key == ord("m"):
                    monitor_requested.set()
    finally:
        controller.shutdown()
        actions.close()
        hotkeys.stop()
        camera.close()
        tracker.close()
        if show_preview:
            preview.close()


def _status(controller: Controller, screen_label: str, fps: float) -> str:
    if not controller.enabled:
        state = "PAUSED"
    elif not controller.poses:
        state = "no hand"
    else:
        state = "  ".join(f"{label[0].upper()}: {pose.value}" for label, pose in controller.poses.items())
        if controller.dragging:
            state += "  (dragging)"
    return f"{state} | {screen_label} | {fps:.0f} fps"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    overrides = {
        name: value
        for name, value in (
            ("camera_index", args.camera),
            ("camera_rotation", args.camera_rotation),
            ("monitor", args.monitor),
            ("hand", args.hand),
            ("cursor_hand", args.cursor_hand),
            ("fullscreen", args.fullscreen),
        )
        if value is not None
    }

    # Before anything reads screen geometry or moves the cursor.
    enable_dpi_awareness()

    if args.list_monitors:
        for i, m in enumerate(list_monitors()):
            shape = "portrait" if m.height > m.width else "landscape"
            print(f"{i}: {m.width}x{m.height} {shape} at ({m.left}, {m.top}){'  primary' if i == 0 else ''}")
        return 0

    try:
        config = load_config(args.config, **overrides)
        mouse = DryRunMouse() if args.dry_run else SystemMouse()
        actions = DryRunActions(config) if args.dry_run else SystemActions(config)
        run(config, mouse, actions, show_preview=not args.no_preview)
    except (ConfigError, CameraError, ModelDownloadError) as e:
        print(f"Error: {e}")
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
