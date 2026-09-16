"""Routing adapter for the preserved pause/resume runtime callback."""

from __future__ import annotations

from .intents import OperatorIntent, OperatorIntentKind
from runtime.ui.commands.models import CommandResult, CommandStatus, DomainIntent


class PauseCommandHandler:
    """Validate pause routing without executing pause or resume semantics."""

    async def route(self, intent: OperatorIntent) -> CommandResult:
        if intent.kind not in {OperatorIntentKind.PAUSE_CHARGE, OperatorIntentKind.RESUME_CHARGE}:
            return CommandResult(CommandStatus.REJECTED, "invalid_pause_intent")
        return CommandResult(
            CommandStatus.ACCEPTED,
            "routed_to_preserved_pause_handler",
            DomainIntent(kind=intent.kind.value, payload=dict(intent.parameters)),
        )
