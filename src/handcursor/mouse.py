"""The ways the controller can act on the system cursor."""

from __future__ import annotations

from typing import Literal, Protocol

Button = Literal["left", "right"]


class Mouse(Protocol):
    def move(self, x: int, y: int) -> None: ...
    def press(self, button: Button) -> None: ...
    def release(self, button: Button) -> None: ...
    def click(self, button: Button) -> None: ...
    def scroll(self, notches: int) -> None: ...


class SystemMouse:
    def __init__(self) -> None:
        # Imported here so that --dry-run and the tests never touch the real input stack.
        from pynput.mouse import Button as PynputButton, Controller

        self._controller = Controller()
        self._buttons = {"left": PynputButton.left, "right": PynputButton.right}

    def move(self, x: int, y: int) -> None:
        self._controller.position = (x, y)

    def press(self, button: Button) -> None:
        self._controller.press(self._buttons[button])

    def release(self, button: Button) -> None:
        self._controller.release(self._buttons[button])

    def click(self, button: Button) -> None:
        self._controller.click(self._buttons[button])

    def scroll(self, notches: int) -> None:
        self._controller.scroll(0, notches)


class DryRunMouse:
    """Prints actions rather than performing them. Moves are left out as too noisy."""

    def move(self, x: int, y: int) -> None:
        pass

    def press(self, button: Button) -> None:
        print(f"[dry run] press {button}")

    def release(self, button: Button) -> None:
        print(f"[dry run] release {button}")

    def click(self, button: Button) -> None:
        print(f"[dry run] click {button}")

    def scroll(self, notches: int) -> None:
        print(f"[dry run] scroll {notches:+d}")
