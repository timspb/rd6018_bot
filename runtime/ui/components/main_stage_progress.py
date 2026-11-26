"""Pure MAIN countdown presentation from an already accepted analyzer clock.

No timer, telemetry, charger execution, storage, panel publisher or configuration
owner lives here. The calling read-model supplies canonical recipe hold duration.
"""
from __future__ import annotations

import math


def main_stage_countdown_status(
    *,
    minimum_a: float,
    elapsed_s: int,
    clock_available: bool,
    tail_ready: bool,
    hold_seconds: float,
    intent: str,
    chemistry: str,
) -> str:
    """Describe the observation; never authorize a stage transition."""
    minimum = f"Imin {minimum_a:.2f} A"
    if not tail_ready:
        return f"✅ {minimum} · ожидание устойчивого CV"
    if hold_seconds is None or not math.isfinite(hold_seconds) or hold_seconds <= 0:
        return f"⏳ {minimum} · время выдержки не подтверждено"
    if not clock_available:
        return f"⏳ {minimum} · время минимума не подтверждено"

    kind = intent.strip().lower()
    chemistry_key = chemistry.strip().upper()
    if chemistry_key == "AGM":
        destination = "решения по MAIN"
    elif kind == "normal":
        destination = "завершения MAIN"
    elif kind in {"recovery", "conditioning"}:
        destination = "MAIN → MIX"
    else:
        destination = "решения по MAIN"

    remaining = max(0, int(math.ceil(hold_seconds - elapsed_s)))
    if not remaining:
        return f"✅ {minimum} · выдержка выполнена, ожидаем решение"
    return (f"✅ {minimum} · до {destination} "
            f"{remaining // 3600}ч {(remaining % 3600) // 60:02d}м")
