"""Pure adopted MIX progress; duration supplied by owner."""
from __future__ import annotations
from typing import Any

def _observer_progress(observer: Any, state: str, regulator: str, *, hold_seconds: float, now_s: float) -> str:
    hold_label = f"{hold_seconds / 3600.0:g}ч"
    if state == "off_pending":
        return "Финиш подтверждён · Output OFF ожидает подтверждения"
    if state == "interrupted":
        return "Подхват прерван перезапуском · требуется новое подтверждение"
    hold_started = getattr(observer, "finish_hold_started_at_s", None)
    if hold_started is not None:
        held_s = max(0.0, now_s - float(hold_started))
        held_m = int(held_s // 60)
        return f"Δ подтверждена · выдержка {held_m // 60}ч {held_m % 60:02d}м / {hold_label}"
    if regulator == "CV":
        return f"Финиш: свежий Imin → ΔI · затем {hold_label} → OFF"
    if regulator == "CC":
        return f"Финиш: свежий Vmax → ΔV · затем {hold_label} → OFF"
    return "Финишный критерий начнёт считаться после подтверждения режима CV/CC"
