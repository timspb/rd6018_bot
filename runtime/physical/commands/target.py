from __future__ import annotations

from .models import CommandTargetValidation, PhysicalCommand, PhysicalCommandTarget


def validate_target(target: PhysicalCommandTarget) -> CommandTargetValidation:
    if target.command not in set(PhysicalCommand):
        return CommandTargetValidation(False, "command_not_allowed")
    if target.command is PhysicalCommand.DISABLE_OUTPUT and target.requested_values:
        return CommandTargetValidation(False, "disable_has_no_setpoint_values")
    if not target.expected_readback:
        return CommandTargetValidation(False, "expected_readback_required")
    missing_tolerance = tuple(field for field in target.expected_readback if field not in target.tolerance)
    if missing_tolerance:
        return CommandTargetValidation(False, "tolerance_required", missing_tolerance)
    invalid_tolerance = tuple(field for field, value in target.tolerance.items() if value < 0)
    if invalid_tolerance:
        return CommandTargetValidation(False, "negative_tolerance", invalid_tolerance)
    if target.timestamp < 0:
        return CommandTargetValidation(False, "timestamp_invalid")
    return CommandTargetValidation(True, "target_valid")
