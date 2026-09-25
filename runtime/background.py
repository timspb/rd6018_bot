"""Small lifecycle primitive for starting already-owned async callbacks.

The runtime owns task creation; callers retain ownership of the callbacks and
their domain state.  No controller, Telegram, HA, or physical dependency is
introduced here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


def start_background_tasks(
    *factories: Callable[[], Awaitable[object]],
) -> tuple[asyncio.Task[object], ...]:
    """Start callbacks in the supplied order and return their task handles."""
    return tuple(asyncio.create_task(factory()) for factory in factories)
