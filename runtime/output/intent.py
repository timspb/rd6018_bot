"""Data-only intent accepted from the safety boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .exceptions import InvalidOutputIntent


class OutputAction(str, Enum):
    ENABLE = "enable_output"
    DISABLE = "disable_output"
    SET_VOLTAGE = "set_voltage"
    SET_CURRENT = "set_current"


@dataclass(frozen=True)
class SafeOutputIntent:
    """A validated permission-shaped value, never a physical command."""

    action: OutputAction
    target_voltage: float | None = None
    target_current: float | None = None
    source: str = "safety"

    def __post_init__(self) -> None:
        try:
            action = self.action if isinstance(self.action, OutputAction) else OutputAction(self.action)
        except ValueError as exc:
            raise InvalidOutputIntent("unknown output action") from exc
        object.__setattr__(self, "action", action)
        if not self.source.strip():
            raise InvalidOutputIntent("output intent source is required")
        if action in {OutputAction.ENABLE, OutputAction.SET_VOLTAGE} and self.target_voltage is None:
            raise InvalidOutputIntent("voltage target is required for this action")
        if action in {OutputAction.ENABLE, OutputAction.SET_CURRENT} and self.target_current is None:
            raise InvalidOutputIntent("current target is required for this action")
        if action == OutputAction.DISABLE and (self.target_voltage is not None or self.target_current is not None):
            raise InvalidOutputIntent("disable action cannot carry setpoints")
        for name, value in (("target_voltage", self.target_voltage), ("target_current", self.target_current)):
            if value is not None and value <= 0:
                raise InvalidOutputIntent(f"{name} must be positive")
