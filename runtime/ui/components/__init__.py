"""Reusable framework-neutral UI components."""

from .journal import (
    collapse_noisy_events,
    format_journal_event,
    normalize_journal_events,
    render_journal_text,
)

__all__ = [
    "collapse_noisy_events",
    "format_journal_event",
    "normalize_journal_events",
    "render_journal_text",
]
