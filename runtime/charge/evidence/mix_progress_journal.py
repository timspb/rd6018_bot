"""Read-only MIX checkpoint summary from existing RD and analyzer evidence.

Called exclusively at the already established 10-minute charge checkpoint.
No timers, actuator access, new persistence or transition decisions.
"""
from __future__ import annotations

from typing import Any, Mapping

from rd6018_telemetry import RegulationMode, finite_float, resolve_regulation


def mix_progress_event(
    live: Mapping[str, Any],
    signal: Mapping[str, Any] | None,
    *,
    stage: str,
    session_id: str | None,
    now_s: float,
    max_age_s: float,
    hold_started_at: float | None = None,
) -> str:
    """Emit factual progress, or an explicit lack of fresh MIX evidence."""
    prefix = "MIX_PROGRESS"
    if not isinstance(signal, Mapping) or signal.get("stage") != stage:
        return prefix + " | evidence=unavailable"

    observed_at = finite_float(signal.get("telemetry_observed_at"))
    if (
        observed_at is None
        or not signal.get("telemetry_valid")
        or now_s < observed_at
        or now_s - observed_at > max_age_s
        or str(signal.get("session_id") or "") != str(session_id or "")
    ):
        return prefix + " | evidence=stale_or_unbound"

    mode = resolve_regulation(live)
    if mode is RegulationMode.UNKNOWN:
        return prefix + " | evidence=fresh | mode=unknown"

    fields = [prefix, "evidence=fresh", f"mode={mode.value.upper()}"]
    if mode is RegulationMode.CV:
        names = (
            ("current_min_a", "Imin", "A"),
            ("delta_current_from_min_a", "delta_a", ""),
            ("reversal_threshold_a", "required_delta_a", ""),
            ("reversal_confirmations", "confirmations", ""),
        )
    else:
        names = (
            ("voltage_max_v", "Vmax", "V"),
            ("delta_voltage_from_max_v", "delta_v", ""),
            ("voltage_reversal_threshold_v", "required_delta_v", ""),
            ("voltage_reversal_confirmations", "confirmations", ""),
        )

    for key, label, suffix in names:
        value = finite_float(signal.get(key))
        if value is not None:
            fields.append(f"{label}={value:.3f}{suffix}" if label != "confirmations"
                          else f"{label}={int(value)}")
    since = finite_float(hold_started_at)
    if since is not None and 0 < since <= now_s:
        fields.append(f"hold_elapsed_s={now_s - since:.1f}")
    return " | ".join(fields)
