from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional, Tuple

from charge_logic import MAX_STAGE_CURRENT
from config import MAX_MANUAL_VOLTAGE


# Legacy bot_legacy.py still contains several historical Vin gates. Production V2
# treats Vin as PSU-health telemetry only (D002), so those gates are neutralized at the
# composition boundary instead of changing rollback/reference code in bot_legacy.py.
LEGACY_VIN_AUTHORITY_DISABLED = float("-inf")


def _finite(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _tick_value(
    controller: Any,
    args: tuple[Any, ...],
    kwargs: Dict[str, Any],
    name: str,
    index: int,
    default: Any,
) -> Any:
    helper = getattr(controller, "_tick_arg", None)
    if callable(helper):
        return helper(args, kwargs, name, index, default)
    if name in kwargs:
        return kwargs[name]
    return args[index] if len(args) > index else default


def _cooling_source_stages(controller: Any) -> set[str]:
    return {
        controller.STAGE_PREP,
        controller.STAGE_MAIN,
        controller.STAGE_DESULFATION,
        controller.STAGE_MIX,
        controller.STAGE_SAFE_WAIT,
    }


def validate_cooling_pause(controller: Any, pause: Any) -> Tuple[bool, str]:
    """Validate durable Cooling continuation authority before any automatic resume.

    A legacy session that only says ``stage=Cooling`` is not enough to reconstruct the
    exact source target and frozen clocks. Missing/corrupt V2 pause metadata therefore
    invalidates automatic resume rather than defaulting to Main.
    """
    if not isinstance(pause, dict):
        return False, "v2_cooling_pause_missing"

    source_stage = str(pause.get("source_stage") or "")
    if source_stage not in _cooling_source_stages(controller):
        return False, "cooling_source_stage_invalid"

    entered_at = _finite(pause.get("entered_at"))
    source_stage_start = _finite(pause.get("source_stage_start_time"))
    if entered_at is None or entered_at <= 0:
        return False, "cooling_entered_at_invalid"
    if source_stage_start is None or source_stage_start <= 0:
        return False, "cooling_source_stage_clock_invalid"

    if source_stage == controller.STAGE_SAFE_WAIT:
        safe_wait_start = _finite(pause.get("source_safe_wait_start"))
        safe_wait_v = _finite(getattr(controller, "_safe_wait_target_v", None))
        safe_wait_i = _finite(getattr(controller, "_safe_wait_target_i", None))
        next_stage = getattr(controller, "_safe_wait_next_stage", None)
        if safe_wait_start is None or safe_wait_start <= 0:
            return False, "cooling_safe_wait_clock_missing"
        if safe_wait_v is None or safe_wait_v <= 0 or safe_wait_i is None or safe_wait_i <= 0:
            return False, "cooling_safe_wait_target_missing"
        if next_stage not in {controller.STAGE_MAIN, controller.STAGE_DONE}:
            return False, "cooling_safe_wait_next_stage_invalid"
        return True, "ok"

    target_v = _finite(pause.get("target_v"))
    target_i = _finite(pause.get("target_i"))
    if target_v is None or target_v <= 0 or target_i is None or target_i <= 0:
        return False, "cooling_source_target_missing"
    if target_v > float(MAX_MANUAL_VOLTAGE) + 1e-9:
        return False, "cooling_source_voltage_over_absolute_ceiling"
    if target_i > float(MAX_STAGE_CURRENT) + 1e-9:
        return False, "cooling_source_current_over_absolute_ceiling"

    envelope_fn = getattr(controller, "_recipe_envelope", None)
    bound_fn = getattr(controller, "_bound_target", None)
    if callable(envelope_fn) and callable(bound_fn):
        try:
            envelope = envelope_fn()
            hv = source_stage in {controller.STAGE_DESULFATION, controller.STAGE_MIX}
            bounded_v, bounded_i = bound_fn((target_v, target_i), envelope, hv=hv)
        except Exception:
            return False, "cooling_source_target_could_not_be_reauthorized"
        if abs(float(bounded_v) - target_v) > 1e-6 or abs(float(bounded_i) - target_i) > 1e-6:
            return False, "cooling_source_target_outside_current_recipe"

    return True, "ok"


def _fail_closed_cooling_actions(controller: Any, reason: str) -> Dict[str, Any]:
    try:
        controller.stop(clear_session=True)
    except Exception:
        # The dispatcher still receives emergency_stop below; never replace a failed
        # state cleanup with permission to continue or re-enable.
        pass
    return {
        "emergency_stop": True,
        "turn_off": True,
        "log_event": f"V2_COOLING_FAIL_CLOSED | {reason}",
        "notify": (
            "🛑 <b>Cooling restore/resume заблокирован.</b> "
            f"Причина: <code>{reason}</code>. Output должен оставаться OFF; "
            "автоматическое продолжение сессии отменено."
        ),
    }


def _install_cooling_guard(controller: Any) -> None:
    if getattr(controller, "_v2_production_cooling_guard_installed", False):
        return

    original_tick = controller.tick
    original_restore = controller.try_restore_session

    async def guarded_tick(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        stage_before = controller.current_stage
        pause_before = (
            dict(controller._v2_cooling_pause)
            if isinstance(getattr(controller, "_v2_cooling_pause", None), dict)
            else None
        )

        # Cooling is the one state that may later emit an automatic Output ON. Never
        # let a missing/corrupt continuation token reach the legacy fallback that
        # defaults an unknown Cooling source to Main.
        if stage_before == controller.STAGE_COOLING:
            valid, reason = validate_cooling_pause(controller, pause_before)
            if not valid:
                return _fail_closed_cooling_actions(controller, reason)

        safe_wait_start_before = (
            _finite(getattr(controller, "_safe_wait_start", None))
            if stage_before == controller.STAGE_SAFE_WAIT
            else None
        )

        actions = await original_tick(*args, **kwargs)
        now = _finite(getattr(controller, "last_update_time", None)) or time.time()
        voltage = _finite(_tick_value(controller, args, kwargs, "voltage", 0, 0.0)) or 0.0
        current = _finite(_tick_value(controller, args, kwargs, "current", 1, 0.0)) or 0.0
        ah = _finite(_tick_value(controller, args, kwargs, "ah", 4, 0.0)) or 0.0

        if (
            stage_before == controller.STAGE_SAFE_WAIT
            and controller.current_stage == controller.STAGE_COOLING
        ):
            pause = getattr(controller, "_v2_cooling_pause", None)
            if not isinstance(pause, dict) or safe_wait_start_before is None or safe_wait_start_before <= 0:
                return _fail_closed_cooling_actions(controller, "safe_wait_cooling_capture_failed")
            pause = dict(pause)
            pause["source_safe_wait_start"] = float(safe_wait_start_before)
            controller._v2_cooling_pause = pause
            valid, reason = validate_cooling_pause(controller, pause)
            if not valid:
                return _fail_closed_cooling_actions(controller, reason)
            # ProductionChargeController already saved once while entering Cooling;
            # save again after adding the SAFE_WAIT-specific frozen clock.
            controller._save_session(voltage, current, ah)
            return actions

        if (
            stage_before == controller.STAGE_COOLING
            and controller.current_stage == controller.STAGE_SAFE_WAIT
        ):
            assert pause_before is not None  # validated before original_tick
            entered_at = float(pause_before["entered_at"])
            source_safe_wait_start = float(pause_before["source_safe_wait_start"])
            cooling_duration = max(0.0, float(now) - entered_at)
            controller._safe_wait_start = source_safe_wait_start + cooling_duration

            # Legacy Cooling resume is designed for energized source stages and emits
            # target programming + turn_on. SAFE_WAIT is explicitly Output OFF, so
            # strip every possible enable/program action and preserve OFF semantics.
            for key in ("turn_on", "set_voltage", "set_current", "set_ovp", "set_ocp"):
                actions.pop(key, None)
            actions["turn_off"] = True
            actions["notify"] = (
                "🌡 АКБ остыла до порога возобновления. SAFE_WAIT продолжается с "
                "замороженным таймером; Output остаётся OFF."
            )
            actions["log_event"] = "COOLING -> SAFE_WAIT | OUTPUT_OFF_PRESERVED"
            controller._save_session(voltage, current, ah)

        return actions

    def guarded_restore(voltage: float, current: float, ah: float):
        ok, message = original_restore(voltage, current, ah)
        if not ok or controller.current_stage != controller.STAGE_COOLING:
            return ok, message

        pause = getattr(controller, "_v2_cooling_pause", None)
        valid, reason = validate_cooling_pause(controller, pause)
        if valid:
            return ok, message

        try:
            controller.stop(clear_session=True)
        finally:
            return (
                False,
                "Cooling session rejected: durable V2 pause state is missing/invalid "
                f"({reason}); automatic resume is disabled and Output must remain OFF.",
            )

    controller.tick = guarded_tick
    controller.try_restore_session = guarded_restore
    controller._v2_production_cooling_guard_installed = True


def install_production_guardrails(app: Any) -> None:
    """Close legacy composition holes without mutating the V1 reference runtime."""
    # Neutralize every historical bot_legacy Vin comparison. Runtime V2 still exposes
    # Vin for PSU-health diagnostics; it simply cannot grant/deny chemistry authority.
    app.MIN_INPUT_VOLTAGE = LEGACY_VIN_AUTHORITY_DISABLED
    app._v2_vin_psu_health_only = True

    controller = getattr(app, "charge_controller", None)
    if controller is None:
        raise RuntimeError("production controller must be installed before guardrails")
    _install_cooling_guard(controller)
    app._v2_production_guardrails_installed = True
