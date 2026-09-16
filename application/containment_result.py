"""Data-only containment result contract for Phase 3 preparation.

This contract is intentionally not wired into watchdogs, safety guards,
SafeOutputCoordinator, the lease, or any physical execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4


class ContainmentVerificationState(str, Enum):
    NOT_REQUESTED = "not_requested"
    REQUESTED = "requested"
    OFF_CONFIRMED = "off_confirmed"
    OFF_UNCONFIRMED = "off_unconfirmed"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ContainmentResult:
    """Immutable description of a containment attempt and its evidence."""

    event_id: str
    trace_id: str
    source: str
    trigger: str
    requested_action: str
    physical_owner: str
    verification_state: ContainmentVerificationState

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "trace_id",
            "source",
            "trigger",
            "requested_action",
            "physical_owner",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
        if not isinstance(self.verification_state, ContainmentVerificationState):
            try:
                object.__setattr__(
                    self,
                    "verification_state",
                    ContainmentVerificationState(self.verification_state),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid verification_state") from exc

    @classmethod
    def new(
        cls,
        *,
        trace_id: str,
        source: str,
        trigger: str,
        requested_action: str,
        physical_owner: str,
        verification_state: ContainmentVerificationState = ContainmentVerificationState.UNKNOWN,
    ) -> "ContainmentResult":
        return cls(
            event_id=uuid4().hex,
            trace_id=trace_id,
            source=source,
            trigger=trigger,
            requested_action=requested_action,
            physical_owner=physical_owner,
            verification_state=verification_state,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "source": self.source,
            "trigger": self.trigger,
            "requested_action": self.requested_action,
            "physical_owner": self.physical_owner,
            "verification_state": self.verification_state.value,
        }
