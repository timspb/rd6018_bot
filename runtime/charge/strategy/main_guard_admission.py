"""Read-only admission of the actual canonical MAIN charge session to Guard shadow.

One production session owner, no new journal, socket or actuator. The logger
invokes this under its existing ExecutionPort owner lock. A stale/foreign
charge_session.json or unmatched physical Iset is NOT a source of authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

from rd6018_telemetry import canonical_programmed_readback, finite_float, telemetry_freshness
from runtime.charge.strategy.main_targets import select_main_target
from runtime.charge.strategy.main_guard_session import GUARD_KEY

MAX_SESSION_AGE_S = 120.0
MAX_NATIVE_AGE_S = 10.0
READBACK_MARGIN_A = 0.02


@dataclass(frozen=True)
class MainGuardAdmission:
    session_id: str
    battery_id: str
    capacity_ah: float
    recipe_initial_current_a: float


def read_canonical_session(path: str | Path) -> Mapping[str, Any] | None:
    """Read one snapshot without modifying the controller or file."""
    file = Path(path)
    try:
        if file.is_symlink() or not file.is_file():
            return None
        document = json.loads(file.read_text(encoding="utf-8"))
        return document if type(document) is dict else None
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def _positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def admit_main_guard_shadow(
    *,
    controller: Any,
    session_document: Mapping[str, Any] | None,
    live: Mapping[str, Any],
    now_epoch_s: float,
) -> MainGuardAdmission | None:
    """Require durable identity, accepted MAIN recipe and native Iset receipt.

    This function NEVER approves hardware changes or journal writes.
    """
    if not isinstance(session_document, Mapping) or not isinstance(live, Mapping):
        return None
    if (getattr(controller, "is_active", False) is not True
            or session_document.get("v2_authoritative") is not True
            or session_document.get("state") == "retired"
            or GUARD_KEY in session_document):
        # Previously guarded sessions require their canonical restore owner.
        return None
    profile = str(getattr(controller, "battery_type", "")).strip().upper()
    if profile not in ("EFB", "CA/CA"):
        return None
    stage = getattr(controller, "STAGE_MAIN", None)
    if not stage or getattr(controller, "current_stage", None) != stage or session_document.get("stage") != stage:
        return None
    session_id = getattr(controller, "_v2_trace_session_id", None)
    battery_id = getattr(controller, "_v2_battery_id", None)
    started = _positive(getattr(controller, "_v2_trace_started_at", None))
    if (type(session_id) is not str or len(session_id) != 32
            or any(ch not in "0123456789abcdef" for ch in session_id)
            or type(battery_id) is not str or not battery_id.strip()
            or battery_id.startswith(("anonymous:", "session:", "runtime:"))
            or started is None or session_document.get("v2_trace_session_id") != session_id
            or session_document.get("v2_battery_id") != battery_id
            or session_document.get("v2_trace_started_at") != started):
        return None
    saved = _positive(session_document.get("saved_at"))
    now = _positive(now_epoch_s)
    if saved is None or now is None or not 0 <= now-saved <= MAX_SESSION_AGE_S:
        return None
    capacity = _positive(getattr(controller, "ah_capacity", None))
    saved_capacity = _positive(session_document.get("ah_limit"))
    if capacity is None or saved_capacity is None or abs(capacity-saved_capacity) > 1e-6:
        return None
    if str(session_document.get("profile", "")).strip().upper() != profile:
        return None
    try:
        recipe = float(select_main_target(profile=profile, capacity_ah=capacity).current_a)
    except (ValueError, TypeError, OverflowError):
        return None
    # Guard's 0.1C baseline must already agree with the accepted recipe:
    # never pretend an initially higher physical setting was limited.
    baseline = min(recipe, .1 * capacity, 12.0)
    if not math.isfinite(recipe) or baseline < .1 or recipe > baseline + READBACK_MARGIN_A:
        return None
    target = _positive(session_document.get("target_current"))
    if target is None or abs(target-recipe) > READBACK_MARGIN_A:
        return None
    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        return None
    keys = ("output_state_code_v2", "current", "set_current_readback_v2", "ocp_readback_v2")
    if not telemetry_freshness(
        live, keys, max_age_s=MAX_NATIVE_AGE_S, max_skew_s=MAX_NATIVE_AGE_S,
        now_epoch_s=now
    ).valid:
        return None
    output = finite_float(live.get("output_state_code_v2"))
    if output != 1:
        return None
    programmed = canonical_programmed_readback(live, "set_current")
    ocp = canonical_programmed_readback(live, "ocp")
    if (programmed is None or ocp is None
            or abs(programmed-target) > READBACK_MARGIN_A
            or programmed > baseline + READBACK_MARGIN_A
            or ocp < programmed):
        return None
    return MainGuardAdmission(session_id, battery_id, capacity, recipe)


__all__ = ["MainGuardAdmission", "admit_main_guard_shadow", "read_canonical_session"]
