"""Compatibility exports for the optional AI integration.

New production code should import from :mod:`integrations.ai`.
"""

from integrations.ai.engine import (
    ask_deepseek,
    format_ai_snapshot,
    format_recent_events,
)

__all__ = ["ask_deepseek", "format_ai_snapshot", "format_recent_events"]
