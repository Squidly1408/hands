"""User-tunable settings. See config.example.toml for what each one does."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


class ConfigError(ValueError):
    pass


DEFAULT_APPS = (
    ("Browser", "open:https://www.google.com"),
    ("Files", "open:explorer"),
    ("Notepad", "open:notepad"),
    ("Calculator", "open:calc"),
    ("On-screen keyboard", "open:osk"),
    ("Settings", "open:ms-settings:"),
    ("Start menu", "keys:<cmd>"),
    ("Task view", "keys:<cmd>+<tab>"),
    ("Show desktop", "keys:<cmd>+d"),
)


@dataclass(frozen=True)
class Config:
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    camera_rotation: int = 0
    monitor: int | str = "all"
    fullscreen: bool = False
    hand: str = "both"
    cursor_hand: str = "right"
    region: tuple[float, float, float, float] = (0.2, 0.25, 0.8, 0.75)
    min_cutoff: float = 1.0
    beta: float = 0.01
    pinch_enter: float = 0.3
    pinch_exit: float = 0.45
    stable_frames: int = 3
    drag_hold: float = 0.35
    hand_lost_grace: float = 0.25
    scroll_speed: float = 30.0
    action_hold: float = 0.5
    ring_pinch_action: str = "launcher"
    pinky_pinch_action: str = "keys:<cmd>+<tab>"
    apps: tuple[tuple[str, str], ...] = DEFAULT_APPS
    toggle_hotkey: str = "<ctrl>+<alt>+h"
    quit_hotkey: str = "<ctrl>+<alt>+q"
    monitor_hotkey: str = "<ctrl>+<alt>+m"

    def __post_init__(self) -> None:
        if self.hand not in ("both", "left", "right"):
            raise ConfigError(f"hand must be both, left or right, not {self.hand!r}")
        if self.cursor_hand not in ("left", "right"):
            raise ConfigError(f"cursor_hand must be left or right, not {self.cursor_hand!r}")
        left, top, right, bottom = self.region
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ConfigError(f"region must be left < right and top < bottom within 0-1: {self.region}")
        if self.pinch_exit <= self.pinch_enter:
            raise ConfigError("pinch_exit must be larger than pinch_enter")
        if self.stable_frames < 1:
            raise ConfigError("stable_frames must be at least 1")
        if self.camera_rotation not in (0, 90, 180, 270):
            raise ConfigError(f"camera_rotation must be 0, 90, 180 or 270, not {self.camera_rotation}")
        if self.monitor != "all" and not (isinstance(self.monitor, int) and self.monitor >= 0):
            raise ConfigError(f"monitor must be all or a monitor number, not {self.monitor!r}")


def load_config(path: Path | None, **overrides: object) -> Config:
    """Build a Config from an optional TOML file, then apply overrides on top."""
    values: dict[str, object] = {}
    if path is not None:
        try:
            with path.open("rb") as f:
                values = tomllib.load(f)
        except OSError as e:
            raise ConfigError(f"Cannot read config file: {e}") from e
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"Invalid TOML in {path}: {e}") from e

    known = {f.name for f in fields(Config)}
    unknown = values.keys() - known
    if unknown:
        raise ConfigError(f"Unknown config keys in {path}: {', '.join(sorted(unknown))}")

    values.update(overrides)
    if "region" in values:
        region = tuple(values["region"])  # type: ignore[arg-type]
        if len(region) != 4:
            raise ConfigError("region must have four values: left, top, right, bottom")
        values["region"] = region
    if "apps" in values:
        apps = tuple(tuple(app) for app in values["apps"])  # type: ignore[union-attr]
        if not all(len(app) == 2 for app in apps):
            raise ConfigError('Each entry in apps must be ["name", "action"]')
        values["apps"] = apps
    return Config(**values)  # type: ignore[arg-type]
