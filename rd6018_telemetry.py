from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence


DEFAULT_CRITICAL_MAX_AGE_S = 20.0
DEFAULT_CRITICAL_MAX_SKEW_S = 12.0


class ProtectionStatus(str, Enum):
    NORMAL = "normal"
    OVP = "ovp"
    OCP = "ocp"
    OPP = "opp"
    UNKNOWN = "unknown"


class RegulationMode(str, Enum):
    CV = "cv"
    CC = "cc"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProtectionState:
    status: ProtectionStatus
    code: Optional[int]
    tripped: bool
    ovp: bool = False
    ocp: bool = False
    opp: bool = False
    unknown: bool = False


@dataclass(frozen=True)
class TelemetryFreshness:
    valid: bool
    detail: str = ""
    max_age_s: Optional[float] = None
    skew_s: Optional[float] = None


def finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "yes", "1"}:
            return True
        if normalized in {"off", "false", "no", "0"}:
            return False
    return None


def _integer_code(value: Any) -> Optional[int]:
    parsed = finite_float(value)
    if parsed is None or abs(parsed - round(parsed)) > 1e-9:
        return None
    return int(round(parsed))


def decode_protection_code(value: Any) -> ProtectionState:
    code = _integer_code(value)
    if code == 0:
        return ProtectionState(ProtectionStatus.NORMAL, code, False)
    if code == 1:
        return ProtectionState(ProtectionStatus.OVP, code, True, ovp=True)
    if code == 2:
        return ProtectionState(ProtectionStatus.OCP, code, True, ocp=True)
    if code == 3:
        return ProtectionState(ProtectionStatus.OPP, code, True, opp=True)
    return ProtectionState(ProtectionStatus.UNKNOWN, code, True, unknown=True)


def resolve_protection(live: Mapping[str, Any]) -> ProtectionState:
    """Prefer raw register 16; support legacy OVP/OCP binary sensors."""
    if live.get("protection_code") not in (None, "", "unknown", "unavailable"):
        return decode_protection_code(live.get("protection_code"))

    ovp = as_bool(live.get("ovp_triggered"))
    ocp = as_bool(live.get("ocp_triggered"))
    if ovp is None or ocp is None:
        return ProtectionState(ProtectionStatus.UNKNOWN, None, True, unknown=True)
    if ovp and ocp:
        # Legacy bitmask decoding turns register value 3 (OPP) into both booleans.
        return ProtectionState(ProtectionStatus.UNKNOWN, None, True, unknown=True)
    if ovp:
        return ProtectionState(ProtectionStatus.OVP, None, True, ovp=True)
    if ocp:
        return ProtectionState(ProtectionStatus.OCP, None, True, ocp=True)
    return ProtectionState(ProtectionStatus.NORMAL, None, False)


def decode_regulation_code(value: Any) -> RegulationMode:
    code = _integer_code(value)
    if code == 0:
        return RegulationMode.CV
    if code == 1:
        return RegulationMode.CC
    return RegulationMode.UNKNOWN


def resolve_regulation(live: Mapping[str, Any]) -> RegulationMode:
    if live.get("regulation_code") not in (None, "", "unknown", "unavailable"):
        return decode_regulation_code(live.get("regulation_code"))

    cv = as_bool(live.get("is_cv"))
    cc = as_bool(live.get("is_cc"))
    if cv is True and cc is not True:
        return RegulationMode.CV
    if cc is True and cv is not True:
        return RegulationMode.CC
    return RegulationMode.UNKNOWN


def _parse_iso_timestamp(value: Any) -> Optional[float]:
    if not value or not isinstance(value, str):
        return None
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def telemetry_freshness(
    live: Mapping[str, Any],
    keys: Sequence[str],
    *,
    max_age_s: float = DEFAULT_CRITICAL_MAX_AGE_S,
    max_skew_s: float = DEFAULT_CRITICAL_MAX_SKEW_S,
    now_epoch_s: Optional[float] = None,
) -> TelemetryFreshness:
    """Fail closed on stale HA values once source metadata is available.

    Home Assistant's ``last_reported`` is the correct heartbeat timestamp because it
    advances whenever an integration writes an entity even if the numerical value did
    not change. ``last_updated`` is retained as a compatibility fallback for older HA
    responses/adapters that do not expose ``last_reported``.
    """
    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        return TelemetryFreshness(True)

    now = time.time() if now_epoch_s is None else float(now_epoch_s)
    timestamps: list[float] = []
    ages: list[float] = []
    for key in keys:
        entry = meta.get(key)
        if not isinstance(entry, Mapping):
            return TelemetryFreshness(False, f"freshness metadata missing for {key}")
        status = str(entry.get("status") or "ok").lower()
        if status != "ok":
            return TelemetryFreshness(False, f"{key} status={status}")
        ts = _parse_iso_timestamp(entry.get("last_reported"))
        if ts is None:
            ts = _parse_iso_timestamp(entry.get("last_updated"))
        if ts is None:
            age_from_meta = finite_float(entry.get("age_s"))
            if age_from_meta is None:
                return TelemetryFreshness(False, f"freshness timestamp missing for {key}")
            age = max(0.0, age_from_meta)
            ts = now - age
        else:
            age = max(0.0, now - ts)
        if age > max_age_s:
            return TelemetryFreshness(False, f"{key} stale age={age:.1f}s>{max_age_s:.1f}s", age)
        timestamps.append(ts)
        ages.append(age)

    skew = max(timestamps) - min(timestamps) if timestamps else 0.0
    if skew > max_skew_s:
        return TelemetryFreshness(
            False,
            f"critical telemetry skew={skew:.1f}s>{max_skew_s:.1f}s",
            max(ages) if ages else None,
            skew,
        )
    return TelemetryFreshness(True, max_age_s=max(ages) if ages else 0.0, skew_s=skew)


V2_CANONICAL_OVERRIDES: Dict[str, str] = {
    "power": "power_v2",
    "temp_int": "temp_int_v2",
    "temp_ext": "temp_ext_v2",
    # Writable ESPHome number entities remain command endpoints. These independent
    # force-updated register mirrors own safety readback value/freshness so a
    # same-value command cannot leave canonical programmed evidence stale forever.
    "set_voltage": "set_voltage_readback_v2",
    "set_current": "set_current_readback_v2",
    "ovp": "ovp_readback_v2",
    "ocp": "ocp_readback_v2",
}


def canonicalize_live(live: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Promote corrected V2 sensors while preserving migration-compatible keys."""
    meta = live.get("_meta") if isinstance(live.get("_meta"), dict) else None
    for canonical, corrected in V2_CANONICAL_OVERRIDES.items():
        value = live.get(corrected)
        if value in (None, "", "unknown", "unavailable"):
            continue
        live[canonical] = value
        if meta is not None and corrected in meta:
            copied = dict(meta[corrected])
            copied["source_key"] = corrected
            meta[canonical] = copied

    protection = resolve_protection(live)
    live["protection_status"] = protection.status.value
    live["protection_tripped"] = protection.tripped
    live["opp_triggered"] = protection.opp
    if live.get("protection_code") not in (None, "", "unknown", "unavailable"):
        live["ovp_triggered"] = protection.ovp
        live["ocp_triggered"] = protection.ocp

    regulation = resolve_regulation(live)
    live["regulation_mode"] = regulation.value
    if live.get("regulation_code") not in (None, "", "unknown", "unavailable"):
        live["is_cv"] = regulation is RegulationMode.CV
        live["is_cc"] = regulation is RegulationMode.CC
        # ``is_cv``/``is_cc`` are compatibility views derived from raw register 17.
        # Their values must therefore carry the same source heartbeat as
        # ``regulation_code``. Leaving stale legacy binary-sensor metadata attached to
        # the newly derived values can pin a coherent-source epoch forever even while
        # the authoritative raw regulation report advances normally.
        if meta is not None and "regulation_code" in meta:
            for derived in ("is_cv", "is_cc"):
                copied = dict(meta["regulation_code"])
                copied["source_key"] = "regulation_code"
                meta[derived] = copied

    if "bridge_uptime" not in live and "uptime" in live:
        live["bridge_uptime"] = live.get("uptime")
        if meta is not None and "uptime" in meta:
            copied = dict(meta["uptime"])
            copied["source_key"] = "uptime"
            meta["bridge_uptime"] = copied
    return live


def calibration_fingerprint(live: Mapping[str, Any]) -> Optional[tuple]:
    keys = (
        "cal_vout_zero",
        "cal_vout_scale",
        "cal_vbat_zero",
        "cal_vbat_scale",
        "cal_iout_zero",
        "cal_iout_scale",
        "cal_ibat_zero",
        "cal_ibat_scale",
    )
    values = tuple(_integer_code(live.get(key)) for key in keys)
    if any(value is None for value in values):
        return None
    return (
        str(live.get("model_number") or ""),
        str(live.get("serial_number") or ""),
        str(live.get("firmware_version") or ""),
        *values,
    )


def relay_path_drop_v(live: Mapping[str, Any]) -> Optional[float]:
    """V_OUT-V_BAT while the internal battery relay path is actively loaded.

    This is an RD internal path trend, not battery/cable resistance and not a Kelvin
    measurement. No resistance is computed until the actual unit is characterized.
    """
    output_on = as_bool(live.get("switch"))
    battery_mode = as_bool(live.get("battery_mode"))
    current = finite_float(live.get("current"))
    v_out = finite_float(live.get("voltage"))
    v_bat = finite_float(live.get("battery_voltage"))
    if output_on is not True or battery_mode is not True:
        return None
    if current is None or current < 1.0 or v_out is None or v_bat is None:
        return None
    return v_out - v_bat


def power_consistency(live: Mapping[str, Any]) -> Optional[Dict[str, float | bool]]:
    v_out = finite_float(live.get("voltage"))
    current = finite_float(live.get("current"))
    power = finite_float(live.get("power"))
    if v_out is None or current is None or power is None:
        return None
    expected = v_out * current
    error = power - expected
    tolerance = max(1.0, abs(expected) * 0.05)
    return {
        "expected_w": expected,
        "reported_w": power,
        "error_w": error,
        "tolerance_w": tolerance,
        "consistent": abs(error) <= tolerance,
    }
