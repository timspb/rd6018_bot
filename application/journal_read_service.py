"""Read-only application service for the operator event journal."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable

from runtime.ui.models import JournalView


class EventJournalReadService:
    def __init__(self, source: Callable[[int | None], Iterable[str]] | None = None) -> None:
        self._source = source

    @staticmethod
    def _default_source(limit: int | None) -> Iterable[str]:
        from charging_log import get_current_session_events, get_recent_events

        return get_current_session_events() if limit is None else get_recent_events(limit)

    def read(self, limit: int | None = 50) -> JournalView:
        if limit is not None and limit < 0:
            raise ValueError("limit must not be negative")
        source = self._source or self._default_source
        try:
            events = tuple(str(item) for item in source(None if limit is None else int(limit)))
        except Exception as exc:
            return JournalView((), f"{type(exc).__name__}: {exc}")
        return JournalView(events)

    async def aread(self, limit: int | None = 50) -> JournalView:
        """Read file backed journal data without blocking the event loop."""
        return await asyncio.to_thread(self.read, limit)


__all__ = ["EventJournalReadService"]
