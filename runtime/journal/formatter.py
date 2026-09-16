"""Compact one-line journal formatting."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import ChargeJournalEntry


def format_entry(entry: ChargeJournalEntry) -> str:
    clock = datetime.fromtimestamp(entry.timestamp, timezone.utc).strftime("%H:%M")
    details = " ".join(f"{key}={value}" for key, value in entry.details.items())
    return " ".join(part for part in (clock, entry.stage + ":", entry.short_message, details) if part)
