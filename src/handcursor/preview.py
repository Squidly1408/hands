"""The on-screen preview: camera feed, tracked hand, active region and status."""

from __future__ import annotations

import cv2
import numpy as np

from handcursor.tracker import TrackedHand

WINDOW = "handcursor"
HINTS = "space pause  m monitor  f fullscreen  q quit"

CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)  # fmt: skip

GREEN = (90, 220, 90)
AMBER = (40, 180, 240)
WHITE = (255, 255, 255)
GREY = (150, 150, 150)


def draw(
    frame: np.ndarray,
    hands: list[TrackedHand],
    steering: str | None,
    region: tuple[float, float, float, float],
    status: str,
    enabled: bool,
) -> None:
    height, width = frame.shape[:2]
    accent = GREEN if enabled else AMBER

    left, top, right, bottom = region
    cv2.rectangle(
        frame,
        (int(left * width), int(top * height)),
        (int(right * width), int(bottom * height)),
        accent,
        1,
    )

    for hand in hands:
        pixels = [(int(x * width), int(y * height)) for x, y in hand.image_points]
        for a, b in CONNECTIONS:
            cv2.line(frame, pixels[a], pixels[b], GREY, 1, cv2.LINE_AA)
        for point in pixels:
            cv2.circle(frame, point, 3, WHITE, -1, cv2.LINE_AA)
        palm = (int(hand.frame.palm[0] * width), int(hand.frame.palm[1] * height))
        cv2.circle(frame, palm, 7, accent if hand.frame.label == steering else GREY, -1, cv2.LINE_AA)

    cv2.rectangle(frame, (0, 0), (width, 30), (30, 30, 30), -1)
    cv2.putText(frame, status, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, accent, 1, cv2.LINE_AA)
    cv2.rectangle(frame, (0, height - 24), (width, height), (30, 30, 30), -1)
    cv2.putText(frame, HINTS, (10, height - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, GREY, 1, cv2.LINE_AA)


def open_window(fullscreen: bool) -> None:
    """Create the window up front: one left to imshow can't be resized or go fullscreen."""
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    set_fullscreen(fullscreen)


def set_fullscreen(fullscreen: bool) -> None:
    mode = cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, mode)


def is_fullscreen() -> bool:
    return cv2.getWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN) == cv2.WINDOW_FULLSCREEN


def show(frame: np.ndarray) -> int:
    """Show the frame and return the pressed key's code, or 255 if none."""
    cv2.imshow(WINDOW, frame)
    return cv2.waitKey(1) & 0xFF


def window_closed() -> bool:
    return cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1


def close() -> None:
    cv2.destroyAllWindows()
