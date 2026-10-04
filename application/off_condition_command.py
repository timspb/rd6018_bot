"""Application handler for operator OFF-condition presets."""

from __future__ import annotations

from typing import Any

from runtime.ui.commands.models import CommandResult, CommandStatus, DomainIntent

from .intents import OperatorIntent, OperatorIntentKind


class OffConditionCommandHandler:
    """Route a named OFF preset to the composed runtime state owner."""

    ALLOWED_PRESETS = frozenset({"time_2h", "i_le_030", "v_ge_162", "clear"})

    def __init__(self, app: Any) -> None:
        self._app = app

    def route(self, intent: OperatorIntent) -> CommandResult:
        if intent.kind is not OperatorIntentKind.SET_OFF_CONDITION:
            return CommandResult(CommandStatus.REJECTED, "wrong_off_condition_intent")
        preset = str(intent.parameters.get("preset") or "")
        if preset not in self.ALLOWED_PRESETS:
            return CommandResult(CommandStatus.REJECTED, "unknown_off_preset")
        apply = getattr(self._app, "_apply_manual_off_preset", None)
        if not callable(apply):
            return CommandResult(CommandStatus.REJECTED, "off_condition_owner_not_wired")
        try:
            detail = str(apply(preset))
        except Exception as exc:
            return CommandResult(
                CommandStatus.REJECTED,
                f"off_condition_failed:{type(exc).__name__}",
            )
        return CommandResult(
            CommandStatus.ACCEPTED,
            detail,
            DomainIntent(
                kind=OperatorIntentKind.SET_OFF_CONDITION.value,
                payload={"preset": preset},
            ),
        )


__all__ = ["OffConditionCommandHandler"]
