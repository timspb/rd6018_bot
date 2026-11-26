"""Typed MIX finish-hold start effect."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class MixFinishHoldEffect:
    now_s: float
    mode: str | None
    finish_evidence: Mapping[str, Any] | None
    notify: str
    log_event: str


def build_mix_finish_hold_effect(
    *,
    now_s: float,
    is_cc: bool,
    is_cv: bool,
    voltage_max_v: float | None,
    delta_voltage_from_max_v: float | None,
    current_min_a: float | None,
    delta_current_from_min_a: float | None,
    session_id: str | None,
    hold_seconds: float | None = None,
    current_reversal_threshold_a: float | None = None,
    voltage_reversal_threshold_v: float | None = None,
) -> MixFinishHoldEffect:
    mode = "CC" if is_cc else ("CV" if is_cv else None)
    finish_evidence: Mapping[str, Any] | None = None

    if mode == "CC":
        reference = voltage_max_v
        accepted_delta = delta_voltage_from_max_v
        evidence = (
            f"Vmax={reference:.3f}В, ΔV={accepted_delta:.3f}В"
            if reference is not None and accepted_delta is not None
            else "CC ΔV подтверждена"
        )
    else:
        reference = current_min_a
        accepted_delta = delta_current_from_min_a
        evidence = (
            f"Imin={reference:.3f}А, ΔI={accepted_delta:.3f}А"
            if reference is not None and accepted_delta is not None
            else "CV ΔI подтверждена"
        )

    if mode in {"CV", "CC"} and reference is not None and accepted_delta is not None:
        finish_evidence = MappingProxyType({
            "version": 1,
            "mode": mode,
            "reference_value": float(reference),
            "accepted_delta": float(accepted_delta),
            "accepted_at": float(now_s),
            "session_id": session_id,
        })

    display_mode = mode or "unknown"
    if hold_seconds is None:
        from runtime.charge.strategy.mix_variables import mix_finish_hold_seconds
        hold_seconds = mix_finish_hold_seconds()
    hold_s = float(hold_seconds)
    hold_label = f"{hold_s / 3600.0:g}ч" if hold_s >= 3600 else f"{hold_s / 60.0:g}м"
    log_fields = [f"mode={display_mode}", f"hold_seconds={hold_s:.1f}"]
    if mode == "CV":
        if current_min_a is not None:
            log_fields.append(f"Imin={current_min_a:.3f}A")
        if delta_current_from_min_a is not None:
            log_fields.append(f"delta_a={delta_current_from_min_a:.3f}")
        if current_reversal_threshold_a is not None:
            log_fields.append(f"required_delta_a={current_reversal_threshold_a:.3f}")
    elif mode == "CC":
        if voltage_max_v is not None:
            log_fields.append(f"Vmax={voltage_max_v:.3f}V")
        if delta_voltage_from_max_v is not None:
            log_fields.append(f"delta_v={delta_voltage_from_max_v:.3f}")
        if voltage_reversal_threshold_v is not None:
            log_fields.append(f"required_delta_v={voltage_reversal_threshold_v:.3f}")
    if session_id:
        log_fields.append(f"session={str(session_id)[:64]}")
    return MixFinishHoldEffect(
        now_s=float(now_s),
        mode=mode,
        finish_evidence=finish_evidence,
        notify=(
            f"<b>🎯 V2 Delta подтверждена</b> ({display_mode}).\n"
            f"{evidence}\nSticky finish-hold: {hold_label}."
        ),
        log_event="V2_FINISH_HOLD_START | " + " | ".join(log_fields),
    )


def apply_mix_finish_hold_effect(
    host: Any,
    effect: MixFinishHoldEffect,
    actions: dict[str, Any],
) -> None:
    host.finish_timer_start = effect.now_s
    host._delta_reported = True
    host._delta_trigger_mode = effect.mode
    if effect.finish_evidence is not None and hasattr(host, "_finish_evidence"):
        host._finish_evidence = dict(effect.finish_evidence)
    actions["notify"] = effect.notify
    actions["log_event"] = effect.log_event


__all__ = [
    "MixFinishHoldEffect",
    "apply_mix_finish_hold_effect",
    "build_mix_finish_hold_effect",
]
