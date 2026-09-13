"""Data-only user command and domain-intent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class CommandStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    BLOCKED_BY_SAFETY = "blocked_by_safety"


@dataclass(frozen=True)
class UserCommand:
    command_id: str
    timestamp: float
    source: str
    user: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(str(value).strip() for value in (self.command_id, self.source, self.user)):
            raise ValueError("command_id, source and user are required")


@dataclass(frozen=True)
class StartChargeCommand(UserCommand):
    profile: str | None = None
    recipe: str | None = None
    confirmed: bool = False


@dataclass(frozen=True)
class StopChargeCommand(UserCommand):
    reason: str = ""
    confirmed: bool = False


@dataclass(frozen=True)
class SelectProfileCommand(UserCommand):
    profile: str = ""
    recipe: str | None = None
    chemistry: str | None = None


@dataclass(frozen=True)
class UpdateChargeSettingsCommand(UserCommand):
    requested_settings: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmSafetyCommand(UserCommand):
    acknowledgement: str = ""
    confirmed: bool = False


@dataclass(frozen=True)
class DomainIntent:
    """Non-actuating intent for runtime/policy processing."""

    kind: str
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult:
    status: CommandStatus
    reason: str
    intent: DomainIntent | None = None
