"""Draws the README's images into docs/images. Run again after changing a gesture.

    python scripts/make_readme_images.py
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from handcursor import preview
from handcursor.control import HandFrame
from handcursor.gestures import PALM_POINTS
from handcursor.tracker import TrackedHand

OUT_DIR = Path(__file__).parent.parent / "docs" / "images"

# Drawn large then shrunk, which gives smooth edges. Coordinates are in a 240x260 card.
CARD = (240, 260)
OUTPUT_SCALE = 2
DRAW_SCALE = 8

BACKGROUND = (48, 36, 30)
SKIN = (222, 230, 238)
EDGE = (120, 98, 84)
ACCENT = preview.GREEN

THUMB, INDEX, MIDDLE, RING, PINKY = range(1, 5), range(5, 9), range(9, 13), range(13, 17), range(17, 21)

OPEN_HAND = {
    0: (120, 228),
    **dict(zip(THUMB, [(88, 205), (68, 180), (53, 157), (42, 135)])),
    **dict(zip(INDEX, [(92, 140), (88, 105), (86, 83), (84, 63)])),
    **dict(zip(MIDDLE, [(115, 133), (115, 95), (115, 71), (115, 49)])),
    **dict(zip(RING, [(138, 137), (140, 100), (142, 77), (144, 57)])),
    **dict(zip(PINKY, [(159, 148), (165, 120), (169, 103), (172, 87)])),
}


def _curled(hand: dict, finger: range) -> None:
    x, y = hand[finger[0]]
    for joint, offset in zip(finger[1:], [(0, -24), (0, -12), (0, 10)]):
        hand[joint] = (x + offset[0], y + offset[1])


def _hand(**fingers: list[tuple[int, int]]) -> dict:
    hand = dict(OPEN_HAND)
    for name, joints in fingers.items():
        hand.update(zip(globals()[name.upper()], joints))
    return hand


def pinch_hand() -> dict:
    return _hand(
        thumb=[(88, 205), (70, 180), (62, 150), (60, 120)],
        index=[(92, 140), (78, 113), (66, 103), (60, 107)],
    )


def right_pinch_hand() -> dict:
    return _hand(
        thumb=[(88, 205), (82, 175), (88, 145), (96, 115)],
        index=[(92, 140), (80, 105), (70, 85), (63, 65)],
        middle=[(115, 133), (112, 105), (104, 93), (98, 99)],
    )


def ring_pinch_hand() -> dict:
    return _hand(
        thumb=[(88, 205), (92, 175), (110, 150), (130, 122)],
        ring=[(138, 137), (141, 112), (137, 101), (131, 106)],
    )


def pinky_pinch_hand() -> dict:
    return _hand(
        thumb=[(88, 205), (100, 180), (125, 165), (148, 140)],
        pinky=[(159, 148), (166, 128), (159, 119), (151, 126)],
    )


def scroll_hand() -> dict:
    hand = _hand(thumb=[(88, 205), (82, 180), (100, 170), (125, 168)])
    _curled(hand, RING)
    _curled(hand, PINKY)
    return hand


def fist_hand() -> dict:
    hand = _hand(thumb=[(88, 205), (78, 180), (95, 168), (128, 168)])
    for finger in (INDEX, MIDDLE, RING, PINKY):
        _curled(hand, finger)
    return hand


class Canvas:
    def __init__(self, size: tuple[int, int] = CARD, corner: int = 16) -> None:
        self.size = size
        self.corner = corner
        self.image = np.full((size[1] * DRAW_SCALE, size[0] * DRAW_SCALE, 3), BACKGROUND, np.uint8)

    def _px(self, point: tuple[float, float]) -> tuple[int, int]:
        return round(point[0] * DRAW_SCALE), round(point[1] * DRAW_SCALE)

    def stroke(self, points: list, width: float, color: tuple) -> None:
        for a, b in zip(points, points[1:]):
            cv2.line(self.image, self._px(a), self._px(b), color, round(width * DRAW_SCALE), cv2.LINE_AA)

    def polygon(self, points: list, color: tuple) -> None:
        cv2.fillPoly(self.image, [np.array([self._px(p) for p in points])], color, cv2.LINE_AA)

    def dot(self, point: tuple[float, float], radius: float, color: tuple) -> None:
        cv2.circle(self.image, self._px(point), round(radius * DRAW_SCALE), color, -1, cv2.LINE_AA)

    def arrow(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        length = np.hypot(end[0] - start[0], end[1] - start[1])
        cv2.arrowedLine(
            self.image, self._px(start), self._px(end), ACCENT, 4 * DRAW_SCALE, cv2.LINE_AA, tipLength=9 / length
        )

    def finished(self) -> np.ndarray:
        """The card shrunk to its final size, with rounded transparent corners."""
        size = (self.size[0] * OUTPUT_SCALE, self.size[1] * OUTPUT_SCALE)
        image = cv2.resize(self.image, size, interpolation=cv2.INTER_AREA)
        mask = np.zeros(self.image.shape[:2], np.uint8)
        radius = self.corner * DRAW_SCALE
        width, height = self.size[0] * DRAW_SCALE, self.size[1] * DRAW_SCALE
        cv2.rectangle(mask, (radius, 0), (width - radius, height), 255, -1)
        cv2.rectangle(mask, (0, radius), (width, height - radius), 255, -1)
        for x in (radius, width - radius):
            for y in (radius, height - radius):
                cv2.circle(mask, (x, y), radius, 255, -1, cv2.LINE_AA)
        alpha = cv2.resize(mask, size, interpolation=cv2.INTER_AREA)
        return np.dstack((image, alpha))


def draw_hand(canvas: Canvas, hand: dict) -> None:
    palm = [hand[i] for i in (0, THUMB[0], INDEX[0], MIDDLE[0], RING[0], PINKY[0])]

    def finger(joints: range, width: float) -> None:
        points = [hand[i] for i in joints]
        canvas.stroke(points, width + 4, EDGE)
        canvas.stroke(points, width, SKIN)

    wrist = [hand[0], (hand[0][0], CARD[1] + 20)]
    canvas.stroke(wrist, 56, EDGE)
    canvas.polygon(palm, EDGE)
    canvas.stroke(palm + palm[:1], 16, EDGE)

    # Fingers folded over the palm belong in front of it, the rest behind.
    in_front = [f for f in (INDEX, MIDDLE, RING, PINKY) if hand[f[3]][1] > hand[f[0]][1] - 20]
    for f, width in ((INDEX, 19), (MIDDLE, 20), (RING, 19), (PINKY, 16)):
        if f not in in_front:
            finger(f, width)

    canvas.stroke(wrist, 52, SKIN)
    canvas.polygon(palm, SKIN)
    canvas.stroke(palm + palm[:1], 12, SKIN)

    for f, width in ((PINKY, 16), (RING, 19), (MIDDLE, 20), (INDEX, 19)):
        if f in in_front:
            finger(f, width)
    finger(THUMB, 21)


def card(hand: dict, *, dots: tuple = (), arrows: tuple = ()) -> np.ndarray:
    canvas = Canvas()
    draw_hand(canvas, hand)
    for point in dots:
        canvas.dot(point, 7, ACCENT)
    for start, end in arrows:
        canvas.arrow(start, end)
    return canvas.finished()


def logo() -> np.ndarray:
    """An open hand with a cursor pointer on the palm."""
    canvas = Canvas(size=(260, 260), corner=52)
    draw_hand(canvas, {i: (x + 23, y) for i, (x, y) in OPEN_HAND.items()})
    tip = (122, 132)
    pointer = [(0, 0), (0, 78), (19, 60), (32, 90), (47, 84), (34, 55), (59, 55)]
    points = [(tip[0] + x, tip[1] + y) for x, y in pointer]
    canvas.stroke(points + points[:1], 10, BACKGROUND)
    canvas.polygon(points, ACCENT)
    return canvas.finished()


def palm_centre(hand: dict) -> tuple[float, float]:
    points = np.array([hand[i] for i in PALM_POINTS], dtype=float)
    return tuple(points.mean(axis=0))


def preview_mockup() -> np.ndarray:
    """The real preview drawing code, over a plain backdrop instead of a webcam frame."""
    width, height = 640, 480
    gradient = np.linspace(70, 35, height, dtype=np.uint8)[:, None, None]
    frame = np.broadcast_to(gradient, (height, width, 3)).copy()

    def tracked(hand: dict, label: str, x_offset: int, mirror: bool) -> TrackedHand:
        pixels = np.array([hand[i] for i in range(21)], dtype=float)
        if mirror:
            pixels[:, 0] = CARD[0] - pixels[:, 0]
        points = (pixels + (x_offset, 130)) / (width, height)
        palm = points[list(PALM_POINTS)].mean(axis=0)
        return TrackedHand(HandFrame((float(palm[0]), float(palm[1])), np.zeros((21, 3)), label), points)

    # The preview is mirrored, so the user's left hand is on the left, thumb inward.
    hands = [tracked(pinch_hand(), "left", 70, True), tracked(OPEN_HAND, "right", 340, False)]
    preview.draw(frame, hands, "right", (0.2, 0.25, 0.8, 0.75), "L: left pinch  R: move | all screens | 30 fps", True)
    return frame


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pinch = pinch_hand()
    right = right_pinch_hand()
    centre = palm_centre(OPEN_HAND)
    images = {
        "move": card(
            OPEN_HAND,
            dots=[centre],
            arrows=[(centre, (centre[0] + 34, centre[1] + d)) for d in (-26, 26)]
            + [(centre, (centre[0] - 34, centre[1] + d)) for d in (-26, 26)],
        ),
        "left-click": card(pinch, dots=[(60, 112)]),
        "drag": card(pinch, dots=[(60, 112)], arrows=[((168, 205), (222, 205)), ((168, 205), (168, 160))]),
        "right-click": card(right, dots=[(97, 107)]),
        "launcher": card(ring_pinch_hand(), dots=[(131, 114)]),
        "task-view": card(pinky_pinch_hand(), dots=[(150, 133)]),
        "scroll": card(scroll_hand(), arrows=[((205, 120), (205, 70)), ((205, 140), (205, 190))]),
        "pause": card(fist_hand()),
    }
    gap = np.zeros((CARD[1] * OUTPUT_SCALE, 24, 4), np.uint8)
    both = np.hstack((cv2.flip(images["left-click"], 1), gap, images["move"]))
    cv2.imwrite(str(OUT_DIR / "both-hands.png"), both)
    cv2.imwrite(str(OUT_DIR / "logo.png"), logo())
    for name, image in images.items():
        cv2.imwrite(str(OUT_DIR / f"gesture-{name}.png"), image)
    cv2.imwrite(str(OUT_DIR / "preview.png"), preview_mockup())
    print(f"Wrote {len(images) + 3} images to {OUT_DIR}")


if __name__ == "__main__":
    main()
