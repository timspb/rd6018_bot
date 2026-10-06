"""Read-only application service for the operator event journal."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from runtime.ui.models import JournalView


class EventJournalReadService:
    def __init__(self, source: Callable[[int], Iterable[str]] | None = None) -> None:
        self._source = source

    @staticmethod
    def _default_source(limit: int) -> Iterable[str]:
        from charging_log import get_recent_events

        return get_recent_events(limit)

    def read(self, limit: int = 50) -> JournalView:
        if limit < 0:
            raise ValueError("limit must not be negative")
        source = self._source or self._default_source
        try:
            events = tuple(str(item) for item in source(int(limit)))
        except Exception as exc:
            return JournalView((), f"{type(exc).__name__}: {exc}")
        return JournalView(events)


__all__ = ["EventJournalReadService"]
