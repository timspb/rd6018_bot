"""Data-only actuator intent and shadow mapping contract.

This module does not execute an intent and deliberately has no HA, ESPHome,
controller, safety or physical-layer imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


class ActuatorOperation(str, Enum):
    OUTPUT_ON = "output_on"
    OUTPUT_OFF = "output_off"
    SET_VOLTAGE = "set_voltage"
    SET_CURRENT = "set_current"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ActuatorIntent:
    """Immutable description of a requested actuator operation."""

    intent_id: str
    trace_id: str
    source: str
    requested_operation: ActuatorOperation
    target: Any
    reason: str
    owner: str
    safety_context: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field_name in ("intent_id", "trace_id", "source", "reason", "owner"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
        if not isinstance(self.requested_operation, ActuatorOperation):
            try:
                object.__setattr__(
                    self,
                    "requested_operation",
                    ActuatorOperation(self.requested_operation),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid requested_operation") from exc
        if not isinstance(self.safety_context, Mapping):
            raise TypeError("safety_context must be a mapping")
        object.__setattr__(self, "safety_context", _freeze(self.safety_context))

    @classmethod
    def new(
        cls,
        *,
        trace_id: str,
        source: str,
        requested_operation: ActuatorOperation,
        target: Any,
        reason: str,
        owner: str,
        safety_context: Mapping[str, Any],
    ) -> "ActuatorIntent":
        return cls(
            intent_id=uuid4().hex,
            trace_id=trace_id,
            source=source,
            requested_operation=requested_operation,
            target=target,
            reason=reason,
            owner=owner,
            safety_context=safety_context,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "trace_id": self.trace_id,
            "source": self.source,
            "requested_operation": self.requested_operation.value,
            "target": _plain(self.target),
            "reason": self.reason,
            "owner": self.owner,
            "safety_context": _plain(self.safety_context),
        }


@dataclass(frozen=True)
class ExistingActuatorRequest:
    """Transport-free observation of a current request before normalization."""

    source: str
    operation: ActuatorOperation
    target: Any
    reason: str
    owner: str
    safety_context: Mapping[str, Any]


def map_existing_request(request: ExistingActuatorRequest, *, trace_id: str) -> ActuatorIntent:
    """Map an existing request to an intent without executing it."""
    return ActuatorIntent.new(
        trace_id=trace_id,
        source=request.source,
        requested_operation=request.operation,
        target=request.target,
        reason=request.reason,
        owner=request.owner,
        safety_context=request.safety_context,
    )

