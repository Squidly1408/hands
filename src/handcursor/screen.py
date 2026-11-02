"""Screen geometry, in the physical pixels that cursor positions use."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from screeninfo import get_monitors
from screeninfo.common import ScreenInfoError

from handcursor.config import ConfigError


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    def clamp(self, x: int, y: int) -> tuple[int, int]:
        return min(max(x, self.left), self.left + self.width - 1), min(max(y, self.top), self.top + self.height - 1)


class Workspace:
    """The monitors the hand maps onto.

    The hand maps to their overall bounding box. Unless the monitors form a neat
    rectangle, that box has areas no cursor can reach, so points there snap to the
    nearest real screen.
    """

    def __init__(self, monitors: Sequence[Rect]) -> None:
        self.monitors = tuple(monitors)
        left = min(m.left for m in monitors)
        top = min(m.top for m in monitors)
        right = max(m.left + m.width for m in monitors)
        bottom = max(m.top + m.height for m in monitors)
        self.bounds = Rect(left, top, right - left, bottom - top)

    def snap(self, x: int, y: int) -> tuple[int, int]:
        return self.monitor_at(x, y).clamp(x, y)

    def monitor_at(self, x: int, y: int) -> Rect:
        """The monitor containing this point or, if it's in a gap, the nearest one."""

        def distance(monitor: Rect) -> int:
            px, py = monitor.clamp(x, y)
            return (px - x) ** 2 + (py - y) ** 2

        return min(self.monitors, key=distance)


def enable_dpi_awareness() -> None:
    """Stop Windows scaling our coordinates. Without this, the cursor can't reach
    the screen edges on a display scaled above 100%, which most laptops are.
    Must run before anything queries the screen or moves the cursor."""
    if sys.platform == "win32":
        PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)


def list_monitors() -> list[Rect]:
    """All monitors, primary first, so index 0 is always the primary. A rotated
    monitor reports its rotated size, so portrait screens need no special handling."""
    monitors = sorted(get_monitors(), key=lambda m: not m.is_primary)
    return [Rect(m.x, m.y, m.width, m.height) for m in monitors]


class ScreenSelection:
    """Which screens are being controlled, kept up to date as the layout changes."""

    def __init__(self, selection: int | str, lister: Callable[[], list[Rect]] = list_monitors) -> None:
        self._lister = lister
        self.monitors = lister()
        if selection != "all" and selection >= len(self.monitors):
            raise ConfigError(f"monitor must be all or below {len(self.monitors)}, not {selection}")
        self.selection = selection

    @property
    def workspace(self) -> Workspace:
        return Workspace(self.monitors if self.selection == "all" else [self.monitors[self.selection]])

    @property
    def label(self) -> str:
        return "all screens" if self.selection == "all" else f"screen {self.selection}"

    def next(self) -> None:
        """Cycle through all screens, then each one in turn."""
        choices = ["all", *range(len(self.monitors))]
        self.selection = choices[(choices.index(self.selection) + 1) % len(choices)]

    def refresh(self) -> bool:
        """Pick up monitors being rotated, plugged in or removed. Returns whether anything changed."""
        try:
            monitors = self._lister()
        except ScreenInfoError:  # Windows can briefly report no monitors while reconfiguring.
            return False
        if not monitors or monitors == self.monitors:
            return False
        self.monitors = monitors
        if self.selection != "all" and self.selection >= len(monitors):
            self.selection = "all"
        return True
