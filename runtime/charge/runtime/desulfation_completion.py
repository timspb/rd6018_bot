"""Typed effect for bounded DESULFATION completion into recovery SAFE_WAIT."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from runtime.charge.session import set_current_stage
from runtime.charge.strategy.recovery_safe_wait import RecoverySafeWaitContinuation
from runtime.charge.strategy.safe_wait_variables import SAFE_WAIT_TARGET_MARGIN_V


@dataclass(frozen=True)
class DesulfationCompletionInput:
    session_id: str | None
    session_generation: float | None
    source_stage: str
    safe_wait_stage: str
    next_stage: str
    main_target_voltage_v: float
    main_target_current_a: float
    recovery_attempt: int
    agm_stage_idx: int
    now_s: float
    ah: float
    voltage_v: float
    measured_current_a: float
    temperature_c: float
    log_event_end: Mapping[str, Any]


@dataclass(frozen=True)
class DesulfationCompletionEffect:
    session_id: str | None
    session_generation: float | None
    source_stage: str
    safe_wait_stage: str
    continuation: RecoverySafeWaitContinuation
    now_s: float
    ah: float
    voltage_v: float
    measured_current_a: float
    temperature_c: float
    action_values: Mapping[str, Any]


def build_desulfation_completion_effect(value: DesulfationCompletionInput) -> DesulfationCompletionEffect:
    continuation = RecoverySafeWaitContinuation(
        source_stage=value.source_stage, next_stage=value.next_stage,
        target_voltage_v=float(value.main_target_voltage_v),
        target_current_a=float(value.main_target_current_a), started_at=float(value.now_s),
        session_id=value.session_id, recovery_attempt=int(value.recovery_attempt),
        agm_stage_idx=int(value.agm_stage_idx), session_generation=value.session_generation,
    )
    threshold = continuation.target_voltage_v - float(SAFE_WAIT_TARGET_MARGIN_V.default)
    return DesulfationCompletionEffect(
        session_id=value.session_id, session_generation=value.session_generation,
        source_stage=value.source_stage, safe_wait_stage=value.safe_wait_stage,
        continuation=continuation, now_s=float(value.now_s), ah=float(value.ah),
        voltage_v=float(value.voltage_v), measured_current_a=float(value.measured_current_a),
        temperature_c=float(value.temperature_c),
        action_values=MappingProxyType({
            "log_event_end": MappingProxyType(dict(value.log_event_end)),
            "turn_off": True,
            "notify": (f"<b>⏸ Десульфатация завершена.</b> Ожидание падения до {threshold:.1f}В. "
                       "Выход выключен."),
            "log_event": "START | INTERMEDIATE_RECOVERY_COMPLETE",
        }),
    )


def apply_desulfation_completion_effect(host: Any, effect: DesulfationCompletionEffect,
                                         actions: dict[str, Any]) -> bool:
    """Commit once after session and source-stage identity validation; never actuates."""
    try:
        generation = float(getattr(host, "_v2_trace_started_at", 0.0))
        expected_generation = float(effect.session_generation)
    except (TypeError, ValueError, OverflowError):
        return False
    if (not effect.session_id or effect.session_id != getattr(host, "_v2_trace_session_id", None)
            or not math.isfinite(generation) or not math.isfinite(expected_generation)
            or generation <= 0 or expected_generation <= 0
            or abs(generation - expected_generation) > 1e-6
            or host.current_stage != effect.source_stage):
        return False
    host._recovery_safe_wait = effect.continuation
    set_current_stage(host, effect.safe_wait_stage)
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._safe_wait_next_stage = effect.continuation.next_stage
    host._safe_wait_target_v = effect.continuation.target_voltage_v
    host._safe_wait_target_i = effect.continuation.target_current_a
    host._safe_wait_start = effect.continuation.started_at
    host._record_safe_wait_sample(effect.now_s, effect.voltage_v,
                                  effect.measured_current_a, effect.temperature_c)
    host._main_sample_evidence.reset()
    actions.update(effect.action_values)
    return True


def complete_desulfation_to_safe_wait(
    host: Any, *, main_target_voltage_v: float, main_target_current_a: float,
    now_s: float, ah: float, voltage_v: float, measured_current_a: float,
    temperature_c: float, actions: dict[str, Any],
) -> bool:
    """Capture and commit the existing DESULFATION completion in one owner."""
    try:
        log_event_end = host._make_log_event_end(
            now_s, ah, voltage_v, measured_current_a, temperature_c,
            "bounded intermediate recovery 2h complete",
        )
        value = DesulfationCompletionInput(
            session_id=host._v2_trace_session_id,
            session_generation=float(host._v2_trace_started_at),
            source_stage=host.STAGE_DESULFATION,
            safe_wait_stage=host.STAGE_SAFE_WAIT,
            next_stage=host.STAGE_MAIN,
            main_target_voltage_v=main_target_voltage_v,
            main_target_current_a=main_target_current_a,
            recovery_attempt=int(host.antisulfate_count),
            agm_stage_idx=int(host._agm_stage_idx),
            now_s=now_s, ah=ah, voltage_v=voltage_v,
            measured_current_a=measured_current_a, temperature_c=temperature_c,
            log_event_end=log_event_end,
        )
        effect = build_desulfation_completion_effect(value)
    except Exception:
        return False
    return apply_desulfation_completion_effect(host, effect, actions)


__all__ = ["DesulfationCompletionEffect", "DesulfationCompletionInput",
           "apply_desulfation_completion_effect", "build_desulfation_completion_effect",
           "complete_desulfation_to_safe_wait"]
