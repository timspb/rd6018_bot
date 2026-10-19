"""Typed PREP -> MAIN stage-entry effect for the residual runtime."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class PrepCompletionInput:
    source_stage: str
    prep_stage: str
    main_stage: str
    now_s: float
    ah: float
    battery_capacity_ah: float
    profile: str
    target_voltage_v: float
    target_current_a: float
    actions: Mapping[str, Any]


@dataclass(frozen=True)
class PrepCompletionEffect:
    source_stage: str
    main_stage: str
    now_s: float
    ah: float
    target_voltage_v: float
    target_current_a: float
    action_values: Mapping[str, Any]


def build_prep_completion_effect(value: PrepCompletionInput) -> PrepCompletionEffect:
    action_values = dict(value.actions)
    event_end = action_values.get("log_event_end")
    if isinstance(event_end, Mapping):
        action_values["log_event_end"] = MappingProxyType(dict(event_end))
    action_values.update({
        "set_voltage": float(value.target_voltage_v),
        "set_current": float(value.target_current_a),
        "notify": (
            "<b>✅ Фаза завершена:</b> Подготовка\n"
            "<b>🚀 Переход к:</b> Main Charge"
        ),
        "log_event": f"START | Емкость: {value.battery_capacity_ah}Ah",
    })
    return PrepCompletionEffect(
        source_stage=str(value.source_stage),
        main_stage=str(value.main_stage),
        now_s=float(value.now_s),
        ah=float(value.ah),
        target_voltage_v=float(value.target_voltage_v),
        target_current_a=float(value.target_current_a),
        action_values=MappingProxyType(action_values),
    )


def apply_prep_completion_effect(host: Any, effect: PrepCompletionEffect, actions: dict[str, Any]) -> bool:
    """Commit one PREP -> MAIN stage edge and preserve the existing action batch."""
    if host.current_stage != effect.source_stage or effect.source_stage != host.STAGE_PREP:
        return False
    host.current_stage = effect.main_stage
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._start_ah = effect.ah
    host._reset_delta_and_blanking(effect.now_s)
    actions.update({
        key: dict(value) if isinstance(value, Mapping) else value
        for key, value in effect.action_values.items()
    })
    return True


__all__ = [
    "PrepCompletionEffect",
    "PrepCompletionInput",
    "apply_prep_completion_effect",
    "build_prep_completion_effect",
]
