"""Pure compact duration formatting for operator stage presentation.

No timer ownership or runtime state.
"""
from __future__ import annotations
from typing import Any

def format_eta_compact(raw_eta: Any) -> str:
    text = str(raw_eta or "").strip()
    if not text or text == "—":
        return "—"
    if ":" in text:
        parts = text.split(":")
        if len(parts) == 2:
            try:
                hours = int(parts[0])
                minutes = int(parts[1])
                if hours > 0:
                    return f"{hours}ч {minutes:02d}м"
                return f"{minutes}м"
            except ValueError:
                return text
    return text

def format_seconds_compact(seconds: Any) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "—"
    if total <= 0:
        return "0м"
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours and minutes:
        return f"{hours}ч {minutes:02d}м"
    if hours:
        return f"{hours}ч"
    return f"{max(1, minutes)}м"
