from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class PhysicalCommand(str, Enum):
    SET_VOLTAGE = "SET_VOLTAGE"
    SET_CURRENT = "SET_CURRENT"
    RESET_PROTECTION = "RESET_PROTECTION"
    DISABLE_OUTPUT = "DISABLE_OUTPUT"


@dataclass(frozen=True)
class PhysicalCommandTarget:
    command: PhysicalCommand
    requested_values: Mapping[str, Any]
    expected_readback: Mapping[str, Any]
    tolerance: Mapping[str, float]
    timestamp: float


@dataclass(frozen=True)
class CommandTargetValidation:
    valid: bool
    reason: str
    fields: tuple[str, ...] = ()
