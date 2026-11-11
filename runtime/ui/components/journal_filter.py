"""Filtering of persisted service rows before operator journal paging."""

from __future__ import annotations
from typing import Iterable

_SERVICE_PREFIXES = (
    "CHECKPOINT", "RESTORE", "SESSION_RESTORE", "V2_START", "SESSION_PAUSE",
    "OPERATOR_PAUSE_RETIRED",
)
_SERVICE_EXACT: set[str] = set()


def _parts(line: str) -> tuple[str, str, str, str, str, str, str]:
    fields = line.split(" | ", 6)
    fields += [""] * (7 - len(fields))
    return tuple(fields[:7])  # type: ignore[return-value]


def is_operator_journal_event(line: str) -> bool:
    """Drop periodic and service-only rows before page slicing/counting."""
    if len(line.split(" | ", 6)) < 7:
        return bool(line.strip())
    event = _parts(line)[6].strip()
    name = event.split(" | ", 1)[0].strip()
    return not (
        name in _SERVICE_EXACT
        or event.startswith("START | V2_")
        or any(name.startswith(p) for p in _SERVICE_PREFIXES)
    )


def operator_journal_events(events: Iterable[str]) -> list[str]:
    """Return recorded operator events in source (chronological) order."""
    return [str(event) for event in events if is_operator_journal_event(str(event))]


def collapse_noisy_events(events: Iterable[str]) -> list[str]:
    """Compatibility helper retained for existing component exports."""
    return list(events)


def normalize_journal_events(events: Iterable[str]) -> list[str]:
    """Normalize to the actual operator-visible persisted events."""
    return operator_journal_events(events)
