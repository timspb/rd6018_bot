"""Presentation-only charge card derived from OperatorStateSnapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .operator_state import OperatorStateSnapshot


def _unknown(value: Any) -> str:
    return "UNKNOWN" if value is None or value == "" else str(value)


def _number(value: float | None, suffix: str = "") -> str:
    return "UNKNOWN" if value is None else f"{float(value):.2f}{suffix}"


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "UNKNOWN"
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes:02d}m {secs:02d}s"


@dataclass(frozen=True)
class ChargeCardViewModel:
    battery_name: str
    phase: str
    mode: str
    voltage: str
    current: str
    ccv: str
    target_condition: str
    ah: str
    elapsed: str
    min_value: str
    max_value: str
    hold_remaining: str

    @classmethod
    def from_snapshot(
        cls,
        snapshot: OperatorStateSnapshot,
        *,
        amp_hours: float | None = None,
        elapsed_seconds: float | None = None,
        minimum_value: float | None = None,
        maximum_value: float | None = None,
        hold_remaining_seconds: float | None = None,
    ) -> "ChargeCardViewModel":
        phase = _unknown(snapshot.current_phase).upper()
        mode = _unknown(snapshot.mode).upper()
        conditions = tuple(snapshot.waiting_conditions or ())
        evidence = tuple(snapshot.phase_evidence or ())
        condition_parts = evidence + conditions
        condition = "; ".join(str(item) for item in condition_parts) if condition_parts else snapshot.explanation
        if phase == "MAIN":
            target = f"{_number(snapshot.target_voltage_v, ' V')} / {_number(snapshot.target_current_a, ' A')} · {_unknown(condition)}"
        elif phase == "MIX":
            target = f"{_number(snapshot.target_voltage_v, ' V')} / {_number(snapshot.target_current_a, ' A')} · {_unknown(condition)}"
        elif phase == "HOLD":
            target = f"condition: {_unknown(condition)}"
        elif phase == "SAFE_WAIT":
            target = f"waiting: {_unknown(condition)}"
        else:
            target = f"{phase}: {_unknown(condition)}"
        return cls(
            battery_name=_unknown(snapshot.battery_identity),
            phase=phase,
            mode=mode,
            voltage=_number(snapshot.telemetry.voltage_v),
            current=_number(snapshot.telemetry.current_a),
            ccv=_unknown(snapshot.telemetry.ccv_state.value if hasattr(snapshot.telemetry.ccv_state, "value") else snapshot.telemetry.ccv_state),
            target_condition=target,
            ah=_number(amp_hours, " Ah"),
            elapsed=_duration(elapsed_seconds),
            min_value=_number(minimum_value),
            max_value=_number(maximum_value),
            hold_remaining=_duration(hold_remaining_seconds),
        )


class ChargeCardFormatter:
    """Format exactly five non-empty lines; diagnostics stay outside the card."""

    def format(self, model: ChargeCardViewModel) -> str:
        min_max = f"MIN={model.min_value}"
        if model.phase == "MIX":
            min_max += f" MAX={model.max_value}"
        return "\n".join(
            (
                f"🔋 {model.battery_name} · {model.phase}  {model.mode}",
                f"⚡ {model.voltage} V  {model.current} A  {model.ccv}",
                f"🎯 {model.target_condition}",
                f"🔋 {model.ah}  t={model.elapsed}",
                f"{min_max} Hold={model.hold_remaining}",
            )
        )


__all__ = ["ChargeCardFormatter", "ChargeCardViewModel"]
