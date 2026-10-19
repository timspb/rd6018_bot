"""Canonical charge sample mirror mutation primitive."""

from __future__ import annotations

from typing import Any


def mark_stage_sample(
    host: Any,
    voltage: float,
    current: float,
    temp: float,
    ah: float,
) -> None:
    host._last_voltage = float(voltage)
    host._last_current = float(current)
    host._last_temp_ext = float(temp)
    host._last_ah = float(ah)
    if host._stage_start_voltage <= 0.0:
        host._stage_start_voltage = float(voltage)
    if host._stage_start_current <= 0.0:
        host._stage_start_current = float(current)
    if host._stage_start_temp <= 0.0:
        host._stage_start_temp = float(temp)


__all__ = ["mark_stage_sample"]
