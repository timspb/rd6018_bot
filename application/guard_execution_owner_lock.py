"""Task-reentrant in-process lock for the future canonical RD6018 execution owner.

This primitive alone does NOT make execution ownership safe. All normal
setpoint/Output-ON and session mutations must use the SAME lock; emergency
OFF must retain an independent route that cannot be starved by a stuck task.
No production caller or binding is installed here.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

_T = TypeVar("_T")


class GuardExecutionOwnerLock(asyncio.Lock):
    """Serialize owners while allowing same-task nested execution calls.

    An ordinary asyncio.Lock cannot be held across a controller transaction
    that calls another lock-taking execution primitive: it self-deadlocks.
    Subclassing asyncio.Lock also preserves the existing Guard transaction
    type-check contract.

    This is intentionally task-reentrant, NOT thread- or process-reentrant.
    Separate tasks must wait, even when spawned by the current owner.
    """

    def __init__(self) -> None:
        super().__init__()
        self._owner_task: asyncio.Task | None = None
        self._depth = 0

    @property
    def owner_task(self) -> asyncio.Task | None:
        return self._owner_task

    @property
    def depth(self) -> int:
        return self._depth

    async def acquire(self) -> bool:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("execution lock needs a live asyncio task")
        if self._owner_task is task:
            self._depth += 1
            return True
        # asyncio.Lock.acquire handles cancellation of waiting tasks.
        await super().acquire()
        self._owner_task = task
        self._depth = 1
        return True

    def release(self) -> None:
        task = asyncio.current_task()
        if task is None or task is not self._owner_task or self._depth <= 0:
            raise RuntimeError("execution owner lock can be released only by its task")
        self._depth -= 1
        if self._depth == 0:
            self._owner_task = None
            super().release()

    async def run(self, operation: Callable[[], Awaitable[_T]]) -> _T:
        """Execute one owner operation under the same task-bound lock."""
        async with self:
            return await operation()


__all__ = ["GuardExecutionOwnerLock"]
