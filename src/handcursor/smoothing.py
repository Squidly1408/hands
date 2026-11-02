"""One Euro filter: heavy smoothing when the hand is still, little lag when it moves fast.

See Casiez et al., "1 Euro Filter" (CHI 2012).
"""

from __future__ import annotations

import math


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> None:
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._value: float | None = None
        self._speed = 0.0
        self._time = 0.0

    def update(self, value: float, now: float) -> float:
        if self._value is None:
            self._value, self._time = value, now
            return value
        dt = now - self._time
        if dt <= 0:
            return self._value
        speed = (value - self._value) / dt
        self._speed += _alpha(self._d_cutoff, dt) * (speed - self._speed)
        cutoff = self._min_cutoff + self._beta * abs(self._speed)
        self._value += _alpha(cutoff, dt) * (value - self._value)
        self._time = now
        return self._value
