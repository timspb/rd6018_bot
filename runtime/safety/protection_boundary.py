"""Canonical Protection boundary.

Raw RD6018 protection registers and legacy HA bits terminate here.  Callers outside
Telemetry/Safety consume only a generic CLEAR/TRIPPED/UNKNOWN verdict and optional
freshness/generation evidence.  No hardware I/O is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from rd6018_telemetry import (
    ProtectionStatus, decode_protection_code, telemetry_freshness,
)


class ProtectionVerdict(str, Enum):
    CLEAR = "clear"
    TRIPPED = "tripped"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProtectionAssessment:
    verdict: ProtectionVerdict
    detail: str
    fresh: bool
    native: bool
    age_s: float | None = None

    @property
    def clear(self) -> bool:
        return self.verdict is ProtectionVerdict.CLEAR

    @property
    def tripped(self) -> bool:
        return self.verdict is ProtectionVerdict.TRIPPED


def _source_keys(live: Mapping[str, Any]) -> tuple[str, ...]:
    # Raw R16 carries OPP evidence; legacy OVP/OCP bits are diagnostic only.
    return ("protection_code",)


def _native_evidence(
    live: Mapping[str, Any],
    keys: tuple[str, ...],
) -> tuple[bool, float | None, tuple[tuple[str, float], ...]]:
    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        return False, None, ()
    ages: list[float] = []
    generations: list[tuple[str, float]] = []
    for index, key in enumerate(keys):
        item = meta.get(key)
        if not isinstance(item, Mapping) or item.get("source") != "esp_native_api":
            return False, None, ()
        if item.get("native_type") not in {"SensorState", "BinarySensorState"}:
            return False, None, ()
        stamp = item.get("subscription_timestamp_monotonic")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            return False, None, ()
        generations.append((f"protection:{index}", float(stamp)))
        age = item.get("age_s")
        if isinstance(age, (int, float)) and not isinstance(age, bool):
            ages.append(float(age))
    return True, (max(ages) if ages else None), tuple(generations)


def assess_protection(
    live: Mapping[str, Any],
    *,
    require_fresh: bool = False,
    require_native: bool = False,
    max_age_s: float = 10.0,
    max_skew_s: float = 10.0,
    now_epoch_s: float | None = None,
) -> ProtectionAssessment:
    if not isinstance(live, Mapping):
        return ProtectionAssessment(
            ProtectionVerdict.UNKNOWN, "protection_snapshot_missing", False, False
        )
    keys = _source_keys(live)
    native, age_s, _ = _native_evidence(live, keys)
    if require_native and not native:
        return ProtectionAssessment(
            ProtectionVerdict.UNKNOWN,
            "protection_native_source_unproven",
            False,
            False,
            age_s,
        )
    fresh = True
    if require_fresh:
        fresh = telemetry_freshness(
            live,
            keys,
            max_age_s=max_age_s,
            max_skew_s=max_skew_s,
            now_epoch_s=now_epoch_s,
        ).valid
        if not fresh:
            return ProtectionAssessment(
                ProtectionVerdict.UNKNOWN,
                "protection_freshness_unproven",
                False,
                native,
                age_s,
            )
    state = decode_protection_code(live.get("protection_code"))
    if state.unknown:
        return ProtectionAssessment(
            ProtectionVerdict.UNKNOWN,
            "protection_state_unknown",
            fresh,
            native,
            age_s,
        )
    if state.status is ProtectionStatus.OPP:
        return ProtectionAssessment(
            ProtectionVerdict.TRIPPED,
            "hardware_opp_tripped",
            fresh,
            native,
            age_s,
        )
    # Hardware OVP/OCP are readable diagnostics, not managed software guards.
    return ProtectionAssessment(
        ProtectionVerdict.CLEAR,
        "ovp_ocp_nonblocking" if state.status in {
            ProtectionStatus.OVP, ProtectionStatus.OCP
        } else "hardware_protection_clear",
        fresh,
        native,
        age_s,
    )


def native_protection_generation(
    live: Mapping[str, Any],
) -> tuple[tuple[str, float], ...]:
    """Return opaque protection evidence generations for an already-validated snapshot.

    This helper does not re-authorize the source. Callers that need Safety authority
    must first use assess_protection(..., require_native=True). Restore permits only
    bind themselves to the generation that was already admitted.
    """
    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        raise ValueError("native protection evidence generation incomplete")
    generation: list[tuple[str, float]] = []
    for index, key in enumerate(_source_keys(live)):
        item = meta.get(key)
        stamp = item.get("subscription_timestamp_monotonic") if isinstance(item, Mapping) else None
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            raise ValueError("native protection evidence generation incomplete")
        generation.append((f"protection:{index}", float(stamp)))
    if not generation:
        raise ValueError("native protection evidence generation incomplete")
    return tuple(generation)


__all__ = [
    "ProtectionAssessment",
    "ProtectionVerdict",
    "assess_protection",
    "native_protection_generation",
]
