"""Shadow operator UI boundary for Phase 8.3.

The adapter translates operator text into OperatorIntent and an immutable
diagnostic result.  It does not dispatch, evaluate, persist, or execute intent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from .diagnostics_domain import (
    DiagnosticCategory,
    DiagnosticEvent,
    DiagnosticSeverity,
    TraceCorrelation,
)
from .intents import OperatorIntent, OperatorIntentKind


class UICommand(str, Enum):
    START = "START"
    STOP = "STOP"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STATUS = "STATUS"


@dataclass(frozen=True)
class OperatorUIResult:
    accepted: bool
    reason: str
    trace_id: str
    intent: OperatorIntent | None
    diagnostic: DiagnosticEvent


class OperatorUIAdapter:
    """Parse shadow commands; no route to domain or infrastructure exists."""

    _KINDS = {
        UICommand.START: OperatorIntentKind.START_CHARGE,
        UICommand.STOP: OperatorIntentKind.STOP_CHARGE,
        UICommand.PAUSE: OperatorIntentKind.PAUSE_CHARGE,
        UICommand.RESUME: OperatorIntentKind.RESUME_CHARGE,
        UICommand.STATUS: OperatorIntentKind.REFRESH_PANEL,
    }

    def parse(self, command: str, *, user: str, source: str = "shadow-ui", trace_id: str | None = None) -> OperatorUIResult:
        trace = trace_id or uuid4().hex
        correlation = TraceCorrelation(trace, f"ui-{uuid4().hex[:12]}")
        parts = str(command).strip().split()
        if not parts or parts[0].upper() not in {item.value for item in UICommand}:
            return self._rejected(trace, correlation, "invalid_ui_command")
        try:
            ui_command = UICommand(parts[0].upper())
            parameters = self._parameters(ui_command, parts[1:])
            intent = OperatorIntent(self._KINDS[ui_command], source, user, parameters)
        except (TypeError, ValueError) as exc:
            return self._rejected(trace, correlation, f"invalid_ui_command:{exc}")
        event = DiagnosticEvent.new(
            category=DiagnosticCategory.OPERATOR,
            event_type="operator_intent_created",
            severity=DiagnosticSeverity.INFO,
            correlation=correlation,
            source="operator-ui-shadow",
            payload={"command": ui_command.value, "intent": intent.kind.value},
        )
        return OperatorUIResult(True, "operator_intent_created", trace, intent, event)

    @staticmethod
    def _parameters(command: UICommand, args: list[str]) -> dict[str, Any]:
        if command is UICommand.START:
            if len(args) != 2:
                raise ValueError("START requires PROFILE and CAPACITY_AH")
            try:
                capacity = float(args[1])
            except ValueError as exc:
                raise ValueError("capacity must be numeric") from exc
            if capacity <= 0:
                raise ValueError("capacity must be positive")
            return {"profile": args[0].upper(), "capacity_ah": capacity}
        if args:
            raise ValueError(f"{command.value} does not accept arguments")
        return {}

    @staticmethod
    def _rejected(trace: str, correlation: TraceCorrelation, reason: str) -> OperatorUIResult:
        event = DiagnosticEvent.new(
            category=DiagnosticCategory.OPERATOR,
            event_type="operator_command_rejected",
            severity=DiagnosticSeverity.WARNING,
            correlation=correlation,
            source="operator-ui-shadow",
            warning_code="INVALID_OPERATOR_COMMAND",
            payload={"reason": reason},
        )
        return OperatorUIResult(False, reason, trace, None, event)


__all__ = ["UICommand", "OperatorUIResult", "OperatorUIAdapter"]
