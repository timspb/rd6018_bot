"""Command validation without runtime or actuator dependencies."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.diagnostics import DiagnosticAuthority

from .models import (
    CommandResult, CommandStatus, ConfirmSafetyCommand, SelectProfileCommand,
    StartChargeCommand, StopChargeCommand, UpdateChargeSettingsCommand, UserCommand,
)


@dataclass(frozen=True)
class CommandContext:
    runtime_active: bool = False
    telemetry_available: bool = True
    authority: DiagnosticAuthority = DiagnosticAuthority.ALLOW
    selected_profile: str | None = None


class CommandValidator:
    def validate(self, command: UserCommand, context: CommandContext) -> CommandResult:
        if context.authority is DiagnosticAuthority.HARD_STOP:
            return CommandResult(CommandStatus.BLOCKED_BY_SAFETY, "hard_stop")
        if isinstance(command, StartChargeCommand):
            if context.runtime_active:
                return CommandResult(CommandStatus.REJECTED, "runtime_already_active")
            if not command.profile and not context.selected_profile:
                return CommandResult(CommandStatus.REJECTED, "profile_required")
            if not context.telemetry_available:
                return CommandResult(CommandStatus.REJECTED, "telemetry_required")
            if not command.confirmed:
                return CommandResult(CommandStatus.REQUIRES_CONFIRMATION, "start_confirmation_required")
        elif isinstance(command, StopChargeCommand):
            if not command.reason.strip():
                return CommandResult(CommandStatus.REJECTED, "stop_reason_required")
            if not command.confirmed:
                return CommandResult(CommandStatus.REQUIRES_CONFIRMATION, "stop_confirmation_required")
        elif isinstance(command, SelectProfileCommand):
            if not command.profile.strip():
                return CommandResult(CommandStatus.REJECTED, "profile_required")
        elif isinstance(command, UpdateChargeSettingsCommand):
            if not command.requested_settings:
                return CommandResult(CommandStatus.REJECTED, "settings_required")
            if context.runtime_active:
                return CommandResult(CommandStatus.REJECTED, "settings_change_requires_idle")
        elif isinstance(command, ConfirmSafetyCommand):
            if not command.acknowledgement.strip() or not command.confirmed:
                return CommandResult(CommandStatus.REQUIRES_CONFIRMATION, "safety_acknowledgement_required")
        return CommandResult(CommandStatus.ACCEPTED, "command_valid")
