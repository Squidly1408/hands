"""The app launcher: large tiles at the cursor, easy to hit with a hand.

Runs as its own process, started by actions.py with the tiles as a JSON argument.
"""

from __future__ import annotations

import json
import math
import sys
import tkinter as tk

from handcursor.actions import Action, parse_action, perform
from handcursor.screen import Rect, Workspace, enable_dpi_awareness, list_monitors

TILE_WIDTH, TILE_HEIGHT = 190, 120
GAP = 10
COLUMNS = 3
AUTO_CLOSE_MS = 20000
# Long enough for Windows to return focus to the previous app, which a shortcut should reach.
ACT_DELAY_MS = 150

BACKGROUND = "#1e2430"
TILE = "#2c3444"
TILE_HOVER = "#3f8f4f"
CLOSE_TILE = "#44303a"
TEXT = "#eef2f6"


def window_size(tiles: int) -> tuple[int, int]:
    rows = math.ceil(tiles / COLUMNS)
    columns = min(tiles, COLUMNS)
    return columns * (TILE_WIDTH + GAP) + GAP, rows * (TILE_HEIGHT + GAP) + GAP


def window_position(monitor: Rect, cursor: tuple[int, int], size: tuple[int, int]) -> tuple[int, int]:
    """Centred on the cursor, but kept fully on the monitor."""
    x = cursor[0] - size[0] // 2
    y = cursor[1] - size[1] // 2
    x = max(monitor.left, min(x, monitor.left + monitor.width - size[0]))
    y = max(monitor.top, min(y, monitor.top + monitor.height - size[1]))
    return x, y


def build(root: tk.Tk, apps: list[tuple[str, str]], on_choose) -> None:
    root.title("handcursor launcher")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=BACKGROUND)

    def tile(index: int, name: str, command, color: str) -> None:
        button = tk.Button(
            root,
            text=name,
            command=command,
            font=("Segoe UI", 15),
            bg=color,
            fg=TEXT,
            activebackground=TILE_HOVER,
            activeforeground=TEXT,
            relief="flat",
            borderwidth=0,
            wraplength=TILE_WIDTH - 20,
        )
        button.bind("<Enter>", lambda _: button.configure(bg=TILE_HOVER))
        button.bind("<Leave>", lambda _: button.configure(bg=color))
        row, column = divmod(index, COLUMNS)
        button.place(
            x=GAP + column * (TILE_WIDTH + GAP),
            y=GAP + row * (TILE_HEIGHT + GAP),
            width=TILE_WIDTH,
            height=TILE_HEIGHT,
        )

    for i, (name, text) in enumerate(apps):
        tile(i, name, lambda action=parse_action(text): on_choose(action), TILE)
    tile(len(apps), "Close", root.destroy, CLOSE_TILE)

    root.bind("<Escape>", lambda _: root.destroy())
    root.after(AUTO_CLOSE_MS, root.destroy)


def main() -> int:
    enable_dpi_awareness()
    from pynput.mouse import Controller

    apps = [tuple(app) for app in json.loads(sys.argv[1])]
    root = tk.Tk()

    def choose(action: Action) -> None:
        root.withdraw()
        root.after(ACT_DELAY_MS, lambda: (perform(action), root.destroy()))

    build(root, apps, choose)

    cursor = Controller().position
    size = window_size(len(apps) + 1)
    x, y = window_position(Workspace(list_monitors()).monitor_at(*cursor), cursor, size)
    root.geometry(f"{size[0]}x{size[1]}+{x}+{y}")
    root.focus_force()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
