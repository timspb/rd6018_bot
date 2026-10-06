"""Post-charge diagnostics and finish-boundary helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FinishIntent:
    next_layer: str
    reason: str
    target_voltage: Optional[float] = None
    target_current: Optional[float] = None


_DEFAULT_PROFILE = {
    "min_window_sec": 15 * 60,
    "min_samples": 4,
    "sample_sec": 300,
    "idle_current_a": 0.05,
    "temp_stable_c": 0.60,
    "watch_slope_mv_min": 4.0,
    "strong_slope_mv_min": 8.0,
    "watch_drop_v": 0.08,
    "strong_drop_v": 0.14,
    "risk_bias": 0.0,
    "confidence_bias": 0.0,
}

_PROFILE_OVERRIDES = {
    "AGM": {
        "min_window_sec": 20 * 60,
        "min_samples": 5,
        "sample_sec": 300,
        "idle_current_a": 0.04,
        "temp_stable_c": 0.45,
        "watch_slope_mv_min": 5.5,
        "strong_slope_mv_min": 10.0,
        "watch_drop_v": 0.12,
        "strong_drop_v": 0.18,
        "risk_bias": -0.10,
        "confidence_bias": -0.05,
    },
    "EFB": {
        **_DEFAULT_PROFILE,
        "risk_bias": 0.10,
        "confidence_bias": 0.05,
    },
    "CA/CA": {
        **_DEFAULT_PROFILE,
        "temp_stable_c": 0.70,
        "watch_slope_mv_min": 3.5,
        "strong_slope_mv_min": 7.0,
        "risk_bias": 0.10,
        "confidence_bias": 0.05,
    },
}


def post_charge_profile_params(profile: str) -> Dict[str, Any]:
    """Return accepted post-charge diagnostic thresholds for a battery profile."""

    profile_key = str(profile or "").strip().upper()
    values = _PROFILE_OVERRIDES.get(profile_key, _DEFAULT_PROFILE)
    return dict(values)


__all__ = ["FinishIntent", "post_charge_profile_params"]
