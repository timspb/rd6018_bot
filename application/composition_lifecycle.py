"""Explicit lifecycle contract for composition roots; no startup side effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable


class CompositionLifecycleState(str, Enum):
    NEW = "NEW"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class CompositionLifecycle:
    """Injected lifecycle callbacks; constructing this object starts nothing."""

    start_callback: Callable[[], Awaitable[None]]
    stop_callback: Callable[[], Awaitable[None]]
    state: CompositionLifecycleState = CompositionLifecycleState.NEW

    def __post_init__(self) -> None:
        if not callable(self.start_callback) or not callable(self.stop_callback):
            raise TypeError("explicit lifecycle callbacks are required")


__all__ = ["CompositionLifecycleState", "CompositionLifecycle"]
