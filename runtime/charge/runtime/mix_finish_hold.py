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

    display_mode = "CC" if is_cc else "CV"
    return MixFinishHoldEffect(
        now_s=float(now_s),
        mode=mode,
        finish_evidence=finish_evidence,
        notify=(
            f"<b>🎯 V2 Delta подтверждена</b> ({display_mode}).\n"
            f"{evidence}\nSticky finish-hold: 2ч."
        ),
        log_event=f"V2_FINISH_HOLD_START | {evidence}",
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
