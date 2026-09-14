"""Routing adapter for the preserved charge-profile selection flow."""

from __future__ import annotations

from .intents import OperatorIntent, OperatorIntentKind
from runtime.ui.commands.models import CommandResult, CommandStatus, DomainIntent


class ProfileCommandHandler:
    """Validate profile selection without starting a charge or changing targets."""

    ALLOWED_PROFILES = frozenset({"AGM", "EFB", "Ca/Ca", "Custom"})

    async def route(self, intent: OperatorIntent) -> CommandResult:
        if intent.kind is not OperatorIntentKind.SELECT_CHARGE_PROFILE:
            return CommandResult(CommandStatus.REJECTED, "invalid_profile_intent")
        profile = str(intent.parameters.get("profile", "")).strip()
        if profile not in self.ALLOWED_PROFILES:
            return CommandResult(CommandStatus.REJECTED, "unsupported_charge_profile")
        return CommandResult(
            CommandStatus.ACCEPTED,
            "routed_to_preserved_profile_handler",
            DomainIntent(kind=OperatorIntentKind.SELECT_CHARGE_PROFILE.value, payload={"profile": profile}),
        )
