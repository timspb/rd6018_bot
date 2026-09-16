"""Routing adapter for the preserved managed-stop callback."""

from __future__ import annotations

from .intents import OperatorIntent, OperatorIntentKind
from runtime.ui.commands.models import CommandResult, CommandStatus, DomainIntent


class StopCommandHandler:
    """Validate STOP routing without executing the managed stop transaction."""

    async def route(self, intent: OperatorIntent) -> CommandResult:
        if intent.kind is not OperatorIntentKind.STOP_CHARGE:
            return CommandResult(CommandStatus.REJECTED, "invalid_stop_intent")
        return CommandResult(
            CommandStatus.ACCEPTED,
            "routed_to_managed_stop_handler",
            DomainIntent(kind=OperatorIntentKind.STOP_CHARGE.value, payload=dict(intent.parameters)),
        )
