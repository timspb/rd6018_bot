"""MIX evidence/read-model mirror updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MixEvidenceMirror:
    current_min_a: float | None
    voltage_max_v: float | None
    apply_current_min: bool
    apply_voltage_max: bool


def build_mix_evidence_mirror(
    *,
    is_cv: bool,
    is_cc: bool,
    current_min_a: float | None,
    voltage_max_v: float | None,
) -> MixEvidenceMirror:
    return MixEvidenceMirror(
        current_min_a=current_min_a,
        voltage_max_v=voltage_max_v,
        apply_current_min=bool(is_cv and current_min_a is not None),
        apply_voltage_max=bool(is_cc and voltage_max_v is not None),
    )


def apply_mix_evidence_mirror(host: Any, mirror: MixEvidenceMirror) -> None:
    if mirror.apply_current_min:
        host.i_min_recorded = mirror.current_min_a
    if mirror.apply_voltage_max:
        host.v_max_recorded = mirror.voltage_max_v


__all__ = [
    "MixEvidenceMirror",
    "apply_mix_evidence_mirror",
    "build_mix_evidence_mirror",
]
