"""Command-to-domain-intent mapping; no actuator intent is produced here."""

from __future__ import annotations

from .models import (
    ConfirmSafetyCommand, DomainIntent, SelectProfileCommand, StartChargeCommand,
    StopChargeCommand, UpdateChargeSettingsCommand, UserCommand,
)
from .validation import CommandContext, CommandValidator


class UserCommandAdapter:
    def __init__(self, validator: CommandValidator | None = None) -> None:
        self.validator = validator or CommandValidator()

    def adapt(self, command: UserCommand, context: CommandContext):
        result = self.validator.validate(command, context)
        if result.status.value != "accepted":
            return result
        if isinstance(command, StartChargeCommand):
            intent = DomainIntent("start_charge", {"profile": command.profile or context.selected_profile, "recipe": command.recipe})
        elif isinstance(command, StopChargeCommand):
            intent = DomainIntent("stop_charge", {"reason": command.reason})
        elif isinstance(command, SelectProfileCommand):
            intent = DomainIntent("select_profile", {"profile": command.profile, "recipe": command.recipe, "chemistry": command.chemistry})
        elif isinstance(command, UpdateChargeSettingsCommand):
            intent = DomainIntent("update_charge_settings", dict(command.requested_settings))
        elif isinstance(command, ConfirmSafetyCommand):
            intent = DomainIntent("confirm_safety", {"acknowledgement": command.acknowledgement})
        else:
            intent = DomainIntent("user_command", dict(command.parameters))
        return type(result)(result.status, result.reason, intent)
