"""Read-only MIX finish-hold status from the durable accepted Delta epoch.

The active regulator can change after a qualifying CV or CC Delta. The accepted
proof's own mode is authoritative for its label; live CV/CC is not its owner.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def mix_finish_hold_status(
    *, snapshot: Mapping[str, Any], started_at: Any,
    hold_seconds: Any, now_s: float,
) -> str:
    """Format a persisted hold without creating a clock or charge authority."""
    start = _finite(started_at)
    duration = _finite(hold_seconds)
    if start is None or start <= 0 or start > now_s or duration is None or duration <= 0:
        return "⏳ Финишная выдержка · время не подтверждено"
    remaining = max(0, math.ceil(duration - (now_s - start)))
    countdown = f"{remaining // 3600}ч {(remaining % 3600) // 60:02d}м"

    evidence = snapshot.get("finish_evidence")
    mode = evidence.get("mode") if isinstance(evidence, Mapping) else None
    confirmed = (
        snapshot.get("delta_reported") is True
        and isinstance(evidence, Mapping)
        and evidence.get("available") is True
        and mode in {"CV", "CC"}
        and _finite(evidence.get("reference_value")) is not None
        and _finite(evidence.get("accepted_delta")) is not None
    )
    if confirmed:
        label = "ΔI" if mode == "CV" else "ΔV"
        return f"✅ {label} подтверждена · до SAFE_WAIT {countdown}"
    return f"⏳ Финишная выдержка · до SAFE_WAIT {countdown} · Δ evidence недоступно"
