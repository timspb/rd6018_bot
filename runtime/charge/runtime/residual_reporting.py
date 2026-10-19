"""Typed pending-log and operator-report effect for residual sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ResidualReportingEffect:
    consume_pending_log: bool
    pending_log_event: Optional[str]
    report_text: Optional[str]
    report_notify_directly: bool
    last_hourly_report_s: Optional[float]


def build_residual_reporting_effect(
    *, pending_log_event: Optional[str], manual_off_active: bool,
    now_s: float, last_hourly_report_s: float, report_interval_s: float,
    elapsed_s: float, current_a: float, temperature_c: float, ah: float,
    existing_notify: Any,
) -> ResidualReportingEffect:
    """Freeze the existing residual pending-log/report decisions and payload."""
    report_text = None
    last_report = None
    if not manual_off_active and now_s - last_hourly_report_s >= report_interval_s:
        last_report = float(now_s)
        report_text = (
            f"⏳ Прошло {elapsed_s / 3600.0:.1f}ч из — лимита этапа. "
            f"Ток: {current_a:.2f} А, T: {temperature_c:.1f}°C, Ah: {ah:.2f}."
        )
    return ResidualReportingEffect(
        consume_pending_log=bool(pending_log_event),
        pending_log_event=pending_log_event,
        report_text=report_text,
        report_notify_directly=bool(report_text and existing_notify),
        last_hourly_report_s=last_report,
    )


def apply_residual_reporting_effect(
    host: Any, effect: ResidualReportingEffect, actions: dict[str, Any],
) -> None:
    """Apply only pending-log/report state and outputs; no physical authority."""
    if effect.consume_pending_log:
        actions["log_event"] = effect.pending_log_event
        host._pending_log_event = None
    if effect.report_text:
        host._last_hourly_report = effect.last_hourly_report_s
        if effect.report_notify_directly:
            host.notify(effect.report_text)
        else:
            actions["notify"] = effect.report_text


__all__ = [
    "ResidualReportingEffect",
    "apply_residual_reporting_effect",
    "build_residual_reporting_effect",
]
