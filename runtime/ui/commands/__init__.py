"""Transport-independent user-command contracts."""

from .models import (
    CommandResult, CommandStatus, ConfirmSafetyCommand, DomainIntent,
    SelectProfileCommand, StartChargeCommand, StopChargeCommand,
    UpdateChargeSettingsCommand, UserCommand,
)
from .validation import CommandContext, CommandValidator
from .adapter import UserCommandAdapter

__all__ = [
    "UserCommand", "StartChargeCommand", "StopChargeCommand", "SelectProfileCommand",
    "UpdateChargeSettingsCommand", "ConfirmSafetyCommand", "CommandResult", "CommandStatus",
    "DomainIntent", "CommandContext", "CommandValidator", "UserCommandAdapter",
]
