"""Optional adapters from the production runtime namespace to AI services."""
from __future__ import annotations

from typing import Any

from application.operator_read_source import OperatorReadSource
from integrations.ai import ask_deepseek, format_ai_snapshot, format_recent_events
from integrations.ai.context import build_ai_analysis_text, build_ai_context_dict, build_ai_context_text, build_trend_summary


def trend(times, voltages, currents):
    return build_trend_summary(times, voltages, currents)


async def analysis(app: Any) -> str:
    return await build_ai_analysis_text(
        OperatorReadSource(app), raw_history=app.get_raw_history,
        trend_summary=trend, stage_snapshot=app._safe_stage_snapshot,
        recent_events=app.get_recent_events, ask_ai=ask_deepseek,
        render_ai_text=lambda result: app._sanitize_telegram_html(
            app._md_to_html(result).replace("<br>", "\r\n").replace("<br/>", "\r\n").replace("<br />", "\r\n")
        ), canonical_bool=app._canonical_bool,
        on_error=lambda exc: app.logger.warning("AI analysis failed: %s", exc),
    )


async def context(app: Any) -> str:
    return await build_ai_context_text(
        OperatorReadSource(app), stage_snapshot=app._safe_stage_snapshot,
        recent_events=app.get_recent_events, format_stage_snapshot=format_ai_snapshot,
        format_events=format_recent_events, canonical_bool=app._canonical_bool,
    )


async def context_dict(app: Any) -> dict[str, Any]:
    return await build_ai_context_dict(
        OperatorReadSource(app), stage_snapshot=app._safe_stage_snapshot,
        on_error=lambda exc: app.logger.warning("get_ai_context_dict: unavailable: %s", exc),
    )
