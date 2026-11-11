"""Pure manual extrema and hold presentation; parameters supplied by Manual owner."""
from __future__ import annotations
from typing import Any
from .hmi_values import _finite

def _manual_extrema_status(manual: Any, regulator: str, *, now_s: float, mix_hold_seconds: float) -> str:
    request = getattr(manual, "request", None)
    mix_hold_label = f"{mix_hold_seconds / 3600.0:g}ч"
    if getattr(request, "operation_mode", "") == "main" and regulator == "CV":
        profile = getattr(request, "profile", None)
        required = int(getattr(getattr(profile, "main", None), "confirmation_count", 1) or 1)
        confirmed = int(getattr(manual, "main_min_confirmations", 0) or 0)
        if confirmed < required:
            return "⏳ Imin не подтверждён"
        minimum = _finite(getattr(manual, "_imin", None))
        minimum_text = f"Imin={minimum:.2f} A" if minimum is not None else "Imin=—"
        hold_started = getattr(manual, "main_min_hold_started_at", None)
        if hold_started is None:
            return f"✅ {minimum_text} подтверждён · hold не начат"
        held_m = max(0, int(max(0.0, now_s - float(hold_started)) // 60))
        hold_hours = _finite(getattr(getattr(profile, "main", None), "hold_hours", None))
        limit_text = f" / {hold_hours:g}ч" if hold_hours is not None else ""
        return f"✅ {minimum_text} подтверждён · hold {held_m // 60}ч {held_m % 60:02d}м{limit_text}"
    if getattr(request, "operation_mode", "") == "mix":
        hold_started = getattr(manual, "finish_hold_started_at", None)
        if hold_started is not None:
            held_s = min(
                mix_hold_seconds,
                max(0.0, now_s - float(hold_started)),
            )
            held_m = int(held_s // 60)
            delta = _finite(getattr(getattr(request, "stop", None), "delta", None))
            if regulator == "CV":
                minimum = _finite(getattr(manual, "_imin", None))
                reference = f"Imin {minimum:.2f}A" if minimum is not None else "Imin —"
                delta_text = f"ΔI {delta:.2f}A" if delta is not None else "ΔI —"
            else:
                maximum = _finite(getattr(manual, "_vmax", None))
                reference = f"Vmax {maximum:.2f}V" if maximum is not None else "Vmax —"
                delta_text = f"ΔV {delta:.2f}V" if delta is not None else "ΔV —"
            return (
                f"✅ {reference} · {delta_text} · "
                f"выдержка {held_m // 60}ч {(held_m % 60):02d}м / {mix_hold_label}"
            )
    if regulator == "CC":
        maximum = _finite(getattr(manual, "_vmax", None))
        if maximum is not None:
            return f"✅ Vmax: {maximum:.2f} V"
    if regulator == "CV":
        minimum = _finite(getattr(manual, "_imin", None))
        if minimum is not None:
            return f"✅ Imin: {minimum:.2f} A"
    return ""
