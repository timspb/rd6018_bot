"""Typed COOLING resume effect for the residual automatic runtime."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class CoolingResumeInput:
    source_stage: str
    return_stage: str
    cooling_stage: str
    now_s: float
    ah: float
    target_voltage_v: Any
    target_current_a: Any
    blanking_seconds: float
    battery_capacity_ah: float
    warning_temperature_c: float
    temperature_c: float
    actions: Mapping[str, Any]


@dataclass(frozen=True)
class CoolingResumeEffect:
    source_stage: str
    return_stage: str
    cooling_stage: str
    now_s: float
    ah: float
    target_voltage_v: Any
    target_current_a: Any
    blanking_seconds: float
    action_values: Mapping[str, Any]


def build_cooling_resume_effect(value: CoolingResumeInput) -> CoolingResumeEffect:
    actions = dict(value.actions)
    event_end = actions.get("log_event_end")
    if isinstance(event_end, Mapping):
        actions["log_event_end"] = MappingProxyType(dict(event_end))
    actions.update({
        "set_voltage": value.target_voltage_v,
        "set_current": value.target_current_a,
        "turn_on": True,
        "notify": (
            "🌡 <b>АКБ ОСТЫЛА - ВОЗВРАТ К ЗАРЯДУ!</b>\n"
            f"Температура: {value.temperature_c:.1f}°C (норма: ≤{value.warning_temperature_c:g}°C)\n"
            f"Возврат к этапу: {value.return_stage}"
        ),
        "log_event": f"START | Емкость: {value.battery_capacity_ah}Ah",
    })
    return CoolingResumeEffect(
        source_stage=str(value.source_stage),
        return_stage=str(value.return_stage),
        cooling_stage=str(value.cooling_stage),
        now_s=float(value.now_s),
        ah=float(value.ah),
        target_voltage_v=value.target_voltage_v,
        target_current_a=value.target_current_a,
        blanking_seconds=float(value.blanking_seconds),
        action_values=MappingProxyType(actions),
    )


def apply_cooling_resume_effect(host: Any, effect: CoolingResumeEffect, actions: dict[str, Any]) -> bool:
    """Commit one COOLING resume edge while leaving execution to its caller."""
    if host.current_stage != effect.source_stage or effect.source_stage != effect.cooling_stage:
        return False
    host.current_stage = effect.return_stage
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._cooling_from_stage = None
    host._blanking_until = effect.now_s + effect.blanking_seconds
    actions.update({
        key: dict(value) if isinstance(value, Mapping) else value
        for key, value in effect.action_values.items()
    })
    return True


__all__ = ["CoolingResumeEffect", "CoolingResumeInput", "apply_cooling_resume_effect", "build_cooling_resume_effect"]
