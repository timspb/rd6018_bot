"""Pure formatting for the operator's existing Manual OFF condition."""

from __future__ import annotations

from typing import Any


def format_operator_off_conditions(state: Any, *, now_s: float) -> str:
    """Render OFF-condition values; the caller owns state and the clock."""
    if all(getattr(state, name) is None for name in (
        "voltage_ge", "voltage_le", "current_le", "current_ge", "time_sec",
    )):
        return ""

    parts = []
    if (
        state.voltage_ge is not None
        and state.voltage_le is not None
        and abs(state.voltage_ge - state.voltage_le) < 0.01
    ):
        parts.append(f"при достижении V {state.voltage_ge:.2f} В")
    else:
        if state.voltage_ge is not None:
            parts.append(f"при V≥{state.voltage_ge:.1f} В")
        if state.voltage_le is not None:
            parts.append(f"при V≤{state.voltage_le:.1f} В")

    if (
        state.current_le is not None
        and state.current_ge is not None
        and abs(state.current_le - state.current_ge) < 0.01
    ):
        parts.append(f"при достижении I {state.current_le:.2f} А")
    else:
        if state.current_le is not None:
            parts.append(f"при I≤{state.current_le:.2f} А")
        if state.current_ge is not None:
            parts.append(f"при I≥{state.current_ge:.2f} А")

    remaining_sec = 0.0
    if state.time_sec is not None:
        remaining_sec = state.start_time + state.time_sec - now_s
        if remaining_sec <= 0:
            parts.append("таймер истёк")
        else:
            h = int(state.time_sec // 3600)
            m = int((state.time_sec % 3600) // 60)
            parts.append(f"таймер {h}:{m:02d}")

    line = "⏹ ВЫКЛ ПО УСЛОВИЮ: " + ", ".join(parts)
    if state.time_sec is not None and remaining_sec > 0:
        h = int(remaining_sec // 3600)
        m = int((remaining_sec % 3600) // 60)
        line += f" | осталось до выкл: {h}:{m:02d}"
    return line


__all__ = ["format_operator_off_conditions"]
