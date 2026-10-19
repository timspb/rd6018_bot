"""Typed MAIN-to-MIX effect construction and application."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from runtime.charge.session import set_current_stage

logger = logging.getLogger("rd6018.charge.main_runtime")


@dataclass(frozen=True)
class MainMixEffectInput:
    previous_stage: str
    mix_stage: str
    reason: str
    now_s: float
    ah: float
    target_voltage_v: float
    target_current_a: float
    ovp_v: float
    ocp_a: float
    log_event_end: Mapping[str, Any]


@dataclass(frozen=True)
class MainMixEffect:
    previous_stage: str
    stage: str
    reason: str
    now_s: float
    ah: float
    target_voltage_v: float
    target_current_a: float
    action_values: Mapping[str, Any]


def build_main_mix_effect(value: MainMixEffectInput) -> MainMixEffect:
    voltage, current = float(value.target_voltage_v), float(value.target_current_a)
    return MainMixEffect(
        previous_stage=str(value.previous_stage), stage=str(value.mix_stage),
        reason=str(value.reason), now_s=float(value.now_s), ah=float(value.ah),
        target_voltage_v=voltage, target_current_a=current,
        action_values=MappingProxyType({
            "log_event_end": MappingProxyType(dict(value.log_event_end)),
            "set_voltage": voltage, "set_current": current,
            "set_ovp": float(value.ovp_v), "set_ocp": float(value.ocp_a),
            "notify": (f"<b>🚀 V2 → Mix Mode</b>\n{value.reason}\n"
                       f"Цель: {voltage:.2f}В / {current:.2f}А; выход по CV ΔI или CC ΔV."),
            "log_event": "START | V2_MIX",
        }),
    )


def apply_main_mix_effect(host: Any, effect: MainMixEffect, actions: dict[str, Any]) -> None:
    """Commit the existing stage mutation; caller retains physical transaction ownership."""
    actions.update(effect.action_values)
    set_current_stage(host, effect.stage)
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._reset_delta_and_blanking(effect.now_s)
    host._main_sample_evidence.reset()
    host.finish_timer_start = None
    host._delta_reported = False
    if hasattr(host, "_finish_evidence"):
        host._finish_evidence = None
    host._phase_current_limit = effect.target_current_a
    logger.info("V2 transition %s -> %s | %s", effect.previous_stage, effect.stage, effect.reason)


__all__ = ["MainMixEffect", "MainMixEffectInput", "apply_main_mix_effect", "build_main_mix_effect"]
