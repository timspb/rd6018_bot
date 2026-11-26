"""Typed MAIN-to-MIX effect construction and application."""

from __future__ import annotations

import logging
import math
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
    log_event_end: Mapping[str, Any]
    transition_evidence: Mapping[str, Any] | None = None


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
    reason = str(value.reason).replace("|", "/").replace("\n", " ").replace("\r", " ").strip()
    evidence_fields = []
    evidence = value.transition_evidence or {}
    for key in (
        "mode", "main_imin_a", "main_hold_age_s", "main_hold_required_s",
        "main_delta_a", "main_required_delta_a", "temperature_c",
    ):
        item = evidence.get(key)
        if key == "mode":
            if item in {"CV", "CC"}:
                evidence_fields.append(f"mode={item}")
            continue
        if isinstance(item, bool) or item is None:
            continue
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            evidence_fields.append(f"{key}={number:.3f}")
    log_event = (
        f"MIX_STARTED | reason={reason} | "
        f"target_voltage_v={voltage:.2f} | target_current_a={current:.2f}"
    )
    if evidence_fields:
        log_event += " | " + " | ".join(evidence_fields)
    return MainMixEffect(
        previous_stage=str(value.previous_stage), stage=str(value.mix_stage),
        reason=reason, now_s=float(value.now_s), ah=float(value.ah),
        target_voltage_v=voltage, target_current_a=current,
        action_values=MappingProxyType({
            "log_event_end": MappingProxyType(dict(value.log_event_end)),
            "set_voltage": voltage, "set_current": current,
            "notify": (f"<b>🚀 V2 → Mix Mode</b>\n{reason}\n"
                       f"Цель: {voltage:.2f}В / {current:.2f}А; выход по CV ΔI или CC ΔV."),
            "log_event": log_event,
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


def apply_main_mix_entry(
    host: Any, *, reason: str, now_s: float, ah: float, voltage_v: float,
    current_a: float, temperature_c: float, target_voltage_v: float,
    target_current_a: float, transition_evidence: Mapping[str, Any] | None = None,
    actions: dict[str, Any],
) -> None:
    """Assemble and apply the existing MAIN MIX entry effect once."""
    effect = build_main_mix_effect(MainMixEffectInput(
        previous_stage=host.current_stage,
        mix_stage=host.STAGE_MIX,
        reason=reason,
        now_s=now_s,
        ah=ah,
        target_voltage_v=target_voltage_v,
        target_current_a=target_current_a,
        transition_evidence=transition_evidence,
        log_event_end=host._make_log_event_end(
            now_s, ah, voltage_v, current_a, temperature_c, reason
        ),
    ))
    apply_main_mix_effect(host, effect, actions)


__all__ = [
    "MainMixEffect", "MainMixEffectInput", "apply_main_mix_effect",
    "apply_main_mix_entry", "build_main_mix_effect",
]
