"""Typed effect for successful completion into final SAFE_WAIT."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from runtime.charge.session import set_current_stage
from runtime.charge.strategy.final_safe_wait import FinalSafeWaitContinuation
from runtime.charge.strategy.safe_wait_variables import SAFE_WAIT_TARGET_MARGIN_V

logger = logging.getLogger("rd6018.charge.final_safe_wait")


@dataclass(frozen=True)
class FinalSafeWaitEntryInput:
    source_stage: str
    safe_wait_stage: str
    next_stage: str
    session_id: str | None
    session_generation: float | None
    target_voltage_v: float
    target_current_a: float
    now_s: float
    voltage_v: float
    current_a: float
    temperature_c: float
    ah: float
    reason: str
    log_event_end: Mapping[str, Any]


@dataclass(frozen=True)
class FinalSafeWaitEntryEffect:
    source_stage: str
    safe_wait_stage: str
    continuation: FinalSafeWaitContinuation
    now_s: float
    ah: float
    voltage_v: float
    current_a: float
    temperature_c: float
    action_values: Mapping[str, Any]


def build_final_safe_wait_entry_effect(
    value: FinalSafeWaitEntryInput,
) -> FinalSafeWaitEntryEffect:
    voltage, current = float(value.target_voltage_v), float(value.target_current_a)
    continuation = FinalSafeWaitContinuation(
        source_stage=str(value.source_stage),
        next_stage=str(value.next_stage),
        target_voltage_v=voltage,
        target_current_a=current,
        started_at=float(value.now_s),
        session_id=value.session_id,
        completion_reason=str(value.reason),
        session_generation=value.session_generation,
    )
    threshold = voltage - float(SAFE_WAIT_TARGET_MARGIN_V.default)
    return FinalSafeWaitEntryEffect(
        source_stage=str(value.source_stage),
        safe_wait_stage=str(value.safe_wait_stage),
        continuation=continuation,
        now_s=float(value.now_s),
        ah=float(value.ah),
        voltage_v=float(value.voltage_v),
        current_a=float(value.current_a),
        temperature_c=float(value.temperature_c),
        action_values=MappingProxyType({
            "log_event_end": MappingProxyType(dict(value.log_event_end)),
            "turn_off": True,
            "notify": (
                f"<b>✅ V2: этап завершён.</b> {value.reason}. "
                f"Ожидание падения до {threshold:.1f}В перед Storage."
            ),
            "log_event": "START | V2_AUTHORITATIVE",
        }),
    )


def apply_final_safe_wait_entry_effect(
    host: Any,
    effect: FinalSafeWaitEntryEffect,
    actions: dict[str, Any],
) -> bool:
    """Validate identity before committing one SAFE_WAIT edge and its OFF intent."""
    try:
        generation = float(getattr(host, "_v2_trace_started_at", None))
        expected_generation = float(effect.continuation.session_generation)
        target_v = float(effect.continuation.target_voltage_v)
        target_i = float(effect.continuation.target_current_a)
        started_at = float(effect.continuation.started_at)
    except (TypeError, ValueError, OverflowError):
        return False
    if (
        effect.source_stage not in {host.STAGE_MAIN, host.STAGE_MIX}
        or host.current_stage != effect.source_stage
        or not effect.continuation.session_id
        or effect.continuation.session_id != getattr(host, "_v2_trace_session_id", None)
        or not all(math.isfinite(item) for item in (generation, expected_generation, target_v, target_i, started_at))
        or generation <= 0
        or expected_generation <= 0
        or target_v <= 0
        or target_i <= 0
        or started_at <= 0
        or abs(generation - expected_generation) > 1e-6
    ):
        return False

    set_current_stage(host, effect.safe_wait_stage)
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._safe_wait_next_stage = effect.continuation.next_stage
    host._safe_wait_target_v = target_v
    host._safe_wait_target_i = target_i
    host._safe_wait_start = effect.continuation.started_at
    host._final_safe_wait = effect.continuation
    host._recovery_safe_wait = None
    host._record_safe_wait_sample(
        effect.now_s, effect.voltage_v, effect.current_a, effect.temperature_c
    )
    host.finish_timer_start = None
    host._main_sample_evidence.reset()
    actions.update(effect.action_values)
    logger.info(
        "V2 transition %s -> %s | %s",
        effect.source_stage,
        effect.safe_wait_stage,
        effect.continuation.completion_reason,
    )
    return True


def apply_final_safe_wait_entry(
    host: Any,
    value: FinalSafeWaitEntryInput,
    actions: dict[str, Any],
) -> bool:
    """Build and commit the one immutable final SAFE_WAIT entry effect."""
    return apply_final_safe_wait_entry_effect(
        host, build_final_safe_wait_entry_effect(value), actions
    )


def apply_mix_completion_to_safe_wait(
    host: Any,
    *,
    now_s: float,
    voltage_v: float,
    current_a: float,
    temperature_c: float,
    ah: float,
    reason: str,
    target_voltage_v: float,
    target_current_a: float,
    actions: dict[str, Any],
) -> bool:
    """Own MIX hold completion evidence and dispatch into final SAFE_WAIT."""
    hold_started_at = host.finish_timer_start
    if hold_started_at is not None:
        logger.info(
            "CHARGE_EVIDENCE kind=delta event=hold_complete mode=%s hold_seconds=%.1f timestamp=%.3f",
            host._delta_trigger_mode or "unknown",
            max(0.0, float(now_s) - float(hold_started_at)),
            now_s,
        )
    value = FinalSafeWaitEntryInput(
        source_stage=host.current_stage,
        safe_wait_stage=host.STAGE_SAFE_WAIT,
        next_stage=host.STAGE_DONE,
        session_id=host._v2_trace_session_id,
        session_generation=host._v2_trace_started_at,
        target_voltage_v=target_voltage_v,
        target_current_a=target_current_a,
        now_s=now_s,
        voltage_v=voltage_v,
        current_a=current_a,
        temperature_c=temperature_c,
        ah=ah,
        reason=reason,
        log_event_end=host._make_log_event_end(
            now_s, ah, voltage_v, current_a, temperature_c, reason
        ),
    )
    return apply_final_safe_wait_entry(host, value, actions)


__all__ = [
    "FinalSafeWaitEntryEffect",
    "FinalSafeWaitEntryInput",
    "apply_final_safe_wait_entry",
    "apply_final_safe_wait_entry_effect",
    "apply_mix_completion_to_safe_wait",
    "build_final_safe_wait_entry_effect",
]
