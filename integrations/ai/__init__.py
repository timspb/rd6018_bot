"""Optional, read-only AI integration for RD6018 operator assistance."""

from .engine import ask_deepseek, format_ai_snapshot, format_recent_events
from .system_prompt import AI_CONSULTANT_SYSTEM_PROMPT
from .context import (build_ai_analysis_text, build_ai_context_dict, build_ai_context_text, build_trend_summary)
from .telegram_dialog import handle_dialog_delivery
from .snapshot import get_ai_stage_snapshot
from .screen import analysis_button_spec, build_analysis_screen

__all__ = [
    "AI_CONSULTANT_SYSTEM_PROMPT",
    "ask_deepseek",
    "format_ai_snapshot",
    "format_recent_events",
    "build_ai_analysis_text",
    "build_ai_context_dict",
    "build_ai_context_text",
    "build_trend_summary",
    "handle_dialog_delivery",
    "get_ai_stage_snapshot",
    "analysis_button_spec",
    "build_analysis_screen",
]
