"""Reusable framework-neutral UI components."""

from .details import render_operator_details_body
from .journal import (
    collapse_noisy_events,
    format_journal_event,
    normalize_journal_events,
    render_journal_text,
)

__all__ = [
    "render_operator_details_body",
    "collapse_noisy_events",
    "format_journal_event",
    "normalize_journal_events",
    "render_journal_text",
]
