from __future__ import annotations

import time
from typing import MutableSequence, Optional, TypeVar

T = TypeVar("T")


class LcgRandom:
    """Tiny deterministic PRNG to avoid platform entropy issues during tests."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.state = (seed if seed is not None else time.time_ns()) & 0x7FFFFFFF

    def randbelow(self, upper: int) -> int:
        if upper <= 0:
            raise ValueError("upper must be positive")
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return self.state % upper

    def randint(self, start: int, end: int) -> int:
        return start + self.randbelow(end - start + 1)

    def shuffle(self, values: MutableSequence[T]) -> None:
        for index in range(len(values) - 1, 0, -1):
            swap_index = self.randbelow(index + 1)
            values[index], values[swap_index] = values[swap_index], values[index]
