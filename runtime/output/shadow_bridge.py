"""V3 output-intent to legacy execution snapshot mapping; shadow only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .intent import OutputAction, SafeOutputIntent


@dataclass(frozen=True)
class LegacyExecutionSnapshot:
    action: str
    target_voltage: float | None = None
    target_current: float | None = None
    ovp: float | None = None
    ocp: float | None = None
    enable: bool = False
    disable: bool = False
    reset_protection: bool = False
    execution_order: tuple[str, ...] = ()
    source: str = "v3-shadow"


class V3OutputBridgeShadow:
    def map(self, intent: SafeOutputIntent) -> LegacyExecutionSnapshot:
        if intent.action is OutputAction.ENABLE:
            order = ("set_voltage", "set_current", "set_protection", "readback", "enable")
            return LegacyExecutionSnapshot(
                intent.action.value, intent.target_voltage, intent.target_current,
                enable=True, execution_order=order, source=intent.source,
            )
        if intent.action is OutputAction.DISABLE:
            return LegacyExecutionSnapshot(
                intent.action.value, disable=True, reset_protection=True,
                execution_order=("disable", "verify_off", "reset_protection"), source=intent.source,
            )
        if intent.action is OutputAction.RESET_PROTECTION:
            return LegacyExecutionSnapshot(
                intent.action.value, ovp=intent.target_ovp, ocp=intent.target_ocp,
                reset_protection=True, execution_order=("reset_protection", "readback"), source=intent.source,
            )
        return LegacyExecutionSnapshot(
            intent.action.value, target_voltage=intent.target_voltage,
            target_current=intent.target_current, execution_order=(intent.action.value,), source=intent.source,
        )


@dataclass(frozen=True)
class OutputParityResult:
    status: str
    fields: tuple[str, ...]
    v3_intent: Mapping[str, Any]
    legacy_snapshot: Mapping[str, Any]
    reason: str = ""


class OutputParityComparator:
    @staticmethod
    def compare(v3: SafeOutputIntent, legacy: LegacyExecutionSnapshot) -> OutputParityResult:
        expected = V3OutputBridgeShadow().map(v3)
        fields = tuple(
            name for name in (
                "action", "target_voltage", "target_current", "ovp", "ocp",
                "enable", "disable", "reset_protection", "execution_order", "source",
            )
            if getattr(expected, name) != getattr(legacy, name)
        )
        v3_snapshot = {"action": v3.action.value, "target_voltage": v3.target_voltage, "target_current": v3.target_current, "source": v3.source}
        legacy_snapshot = {name: getattr(legacy, name) for name in ("action", "target_voltage", "target_current", "ovp", "ocp", "enable", "disable", "reset_protection", "execution_order", "source")}
        return OutputParityResult("MATCH" if not fields else "MISMATCH", fields, v3_snapshot, legacy_snapshot, "mapping_equal" if not fields else "mapping_differs")
