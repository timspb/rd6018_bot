"""Typed fail-closed STOP_AND_DIAGNOSE stage effect."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from runtime.charge.terminal_intent import (
    DONE_COMPLETION_TERMINAL,
    DONE_OUTPUT_OFF,
    TerminalPersistenceRequest,
)

logger = logging.getLogger("rd6018.recovery")


@dataclass(frozen=True)
class StopDiagnoseInput:
    source_stage: str
    done_stage: str
    now_s: float
    voltage_v: float
    current_a: float
    temperature_c: float
    ah: float
    reason: str
    log_event_end: Mapping[str, Any]


@dataclass(frozen=True)
class StopDiagnoseEffect:
    source_stage: str
    done_stage: str
    now_s: float
    voltage_v: float
    current_a: float
    ah: float
    reason: str
    log_event_end: Mapping[str, Any]
    action_values: Mapping[str, Any]


def build_stop_diagnose_effect(value: StopDiagnoseInput) -> StopDiagnoseEffect:
    return StopDiagnoseEffect(
        source_stage=str(value.source_stage),
        done_stage=str(value.done_stage),
        now_s=float(value.now_s),
        voltage_v=float(value.voltage_v),
        current_a=float(value.current_a),
        ah=float(value.ah),
        reason=str(value.reason),
        log_event_end=MappingProxyType(dict(value.log_event_end)),
        action_values=MappingProxyType({
            "turn_off": True,
            "notify": (
                "<b>🛑 V2 остановил автоматическую эскалацию.</b>\n"
                f"Причина: <code>{value.reason}</code>.\n"
                "Выход выключен; требуется оценка графика/АКБ перед новым HV-этапом."
            ),
            "log_event": "V2_STOP_DIAGNOSE",
        }),
    )


def apply_stop_diagnose_effect(
    host: Any,
    effect: StopDiagnoseEffect,
    actions: dict[str, Any],
) -> None:
    host._recovery_safe_wait = None
    host._final_safe_wait = None
    actions["log_event_end"] = dict(effect.log_event_end)
    host.current_stage = effect.done_stage
    host._clear_restored_targets()
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host.finish_timer_start = None
    host._main_sample_evidence.reset()
    actions.update(effect.action_values)
    host._save_session(
        effect.voltage_v, effect.current_a, effect.ah,
        terminal_request=TerminalPersistenceRequest(
            DONE_COMPLETION_TERMINAL, DONE_OUTPUT_OFF,
            effect.voltage_v, effect.current_a, effect.ah,
        ),
    )
    logger.warning(
        "Modular diagnostic stop %s -> Done | %s",
        effect.source_stage,
        effect.reason,
    )


def apply_stop_and_diagnose(
    host: Any,
    *,
    actions: dict[str, Any],
    now: float,
    voltage: float,
    current: float,
    temp: float,
    ah: float,
    reason: str,
) -> None:
    value = StopDiagnoseInput(
        source_stage=host.current_stage,
        done_stage=host.STAGE_DONE,
        now_s=now,
        voltage_v=voltage,
        current_a=current,
        temperature_c=temp,
        ah=ah,
        reason=reason,
        log_event_end=host._make_log_event_end(
            now, ah, voltage, current, temp, reason
        ),
    )
    apply_stop_diagnose_effect(host, build_stop_diagnose_effect(value), actions)


__all__ = [
    "StopDiagnoseEffect",
    "StopDiagnoseInput",
    "apply_stop_and_diagnose",
    "apply_stop_diagnose_effect",
    "build_stop_diagnose_effect",
]
