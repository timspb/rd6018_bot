"""Typed MAIN-to-DESULFATION stage effect construction and application."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from runtime.charge.session import set_current_stage
from runtime.charge.strategy.desulfation_variables import DESULFATION_OCP_MARGIN_A
from runtime.safety.variables import PROTECTION_OVP_MARGIN_V

logger = logging.getLogger("rd6018.charge.main_runtime")


@dataclass(frozen=True)
class MainDesulfationEffectInput:
    previous_stage: str
    desulfation_stage: str
    attempt: int
    reason: str
    now_s: float
    ah: float
    target_voltage_v: float
    target_current_a: float
    log_event_end: Mapping[str, Any]


@dataclass(frozen=True)
class MainDesulfationEffect:
    previous_stage: str
    stage: str
    attempt: int
    reason: str
    now_s: float
    ah: float
    target_voltage_v: float
    target_current_a: float
    action_values: Mapping[str, Any]


def build_main_desulfation_effect(value: MainDesulfationEffectInput) -> MainDesulfationEffect:
    """Build the established action payload without mutating runtime state."""
    voltage = float(value.target_voltage_v)
    current = float(value.target_current_a)
    return MainDesulfationEffect(
        previous_stage=value.previous_stage,
        stage=value.desulfation_stage,
        attempt=int(value.attempt),
        reason=str(value.reason),
        now_s=float(value.now_s),
        ah=float(value.ah),
        target_voltage_v=voltage,
        target_current_a=current,
        action_values=MappingProxyType({
            "log_event_end": MappingProxyType(dict(value.log_event_end)),
            "set_voltage": voltage,
            "set_current": current,
            "set_ovp": voltage + float(PROTECTION_OVP_MARGIN_V.default),
            "set_ocp": current + float(DESULFATION_OCP_MARGIN_A.default),
            "notify": (
                f"🔧 <b>V2 десульфатация #{int(value.attempt)}</b>\n"
                f"{value.reason}\nЦель: {voltage:.2f}В / {current:.2f}А на сервисный этап."
            ),
            "log_event": "START | V2_DESULFATION",
        }),
    )


def apply_main_desulfation_effect(host: Any, effect: MainDesulfationEffect, actions: dict[str, Any]) -> None:
    """Apply the sole in-memory stage commit; physical intents remain for caller."""
    host.antisulfate_count = effect.attempt
    actions.update(effect.action_values)
    set_current_stage(host, effect.stage)
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._reset_delta_and_blanking(effect.now_s)
    host._main_sample_evidence.reset()
    host._phase_current_limit = effect.target_current_a
    logger.info("V2 transition %s -> %s | %s", effect.previous_stage, effect.stage, effect.reason)


def apply_main_desulfation_entry(
    host: Any, *, reason: str, now_s: float, ah: float, voltage_v: float,
    current_a: float, temperature_c: float, target_voltage_v: float,
    target_current_a: float, actions: dict[str, Any],
) -> None:
    """Assemble and apply the existing MAIN desulfation entry effect once."""
    effect = build_main_desulfation_effect(MainDesulfationEffectInput(
        previous_stage=host.current_stage,
        desulfation_stage=host.STAGE_DESULFATION,
        attempt=host.antisulfate_count + 1,
        reason=reason,
        now_s=now_s,
        ah=ah,
        target_voltage_v=target_voltage_v,
        target_current_a=target_current_a,
        log_event_end=host._make_log_event_end(
            now_s, ah, voltage_v, current_a, temperature_c, reason
        ),
    ))
    apply_main_desulfation_effect(host, effect, actions)


__all__ = [
    "MainDesulfationEffect", "MainDesulfationEffectInput",
    "apply_main_desulfation_effect", "apply_main_desulfation_entry",
    "build_main_desulfation_effect",
]
