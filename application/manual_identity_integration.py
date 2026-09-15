"""Minimal Manual identity integration adapter.

The adapter owns only lifecycle identity and in-memory canonical event
correlation.  It has no persistence, transport, actuator or FSM decisions.
"""

from __future__ import annotations

from dataclasses import asdict
from time import time
from typing import Any, Mapping
from uuid import uuid4

from v3_core.canonical_events import CanonicalChargeEvent, EventType

from .manual_session_identity_contract import (
    ManualRestoreDecision,
    ManualSessionEvent,
    ManualSessionEventBridge,
    ManualSessionIdentityBoundary,
    ManualSessionIdentityBoundaryContract,
)


class ManualIdentityIntegrationAdapter:
    """Attach identity to an existing Manual manager without changing control."""

    def __init__(self) -> None:
        self._contract = ManualSessionIdentityBoundaryContract()
        self._bridge = ManualSessionEventBridge()
        self._identity: ManualSessionIdentityBoundary | None = None
        self._events: list[CanonicalChargeEvent] = []

    @property
    def identity(self) -> ManualSessionIdentityBoundary | None:
        return self._identity

    @property
    def events(self) -> tuple[CanonicalChargeEvent, ...]:
        return tuple(self._events)

    def create_for_start(self, *, profile: str | None, source: str = "manual", created_at: float | None = None) -> ManualSessionIdentityBoundary:
        identity = self._contract.new_start(
            session_id=uuid4().hex,
            trace_id=uuid4().hex,
            created_at=float(created_at if created_at is not None else time()),
            source=source,
            profile=profile,
        )
        self._identity = identity
        self._events.clear()
        return identity

    def restore(self, persisted: Mapping[str, Any] | None, *, now: float | None = None) -> ManualRestoreDecision:
        decision = self._contract.restore(dict(persisted or {}), now=float(now if now is not None else time()))
        self._identity = decision.identity
        if decision.identity is None:
            self._events.clear()
        return decision

    def emit(self, *, event_type: EventType, timestamp: float | None = None, phase_before: str | None = None, phase_after: str | None = None, reason: str | None = None) -> CanonicalChargeEvent:
        if self._identity is None:
            raise ValueError("cannot emit Manual canonical event without identity")
        event = self._bridge.to_canonical(
            ManualSessionEvent(event_type.value, float(timestamp if timestamp is not None else time()), self._identity, phase_before, phase_after, reason),
            event_id=uuid4().hex,
        )
        self._events.append(event)
        return event

    def identity_payload(self) -> dict[str, Any] | None:
        if self._identity is None:
            return None
        payload = asdict(self._identity)
        payload["origin"] = self._identity.origin.value
        return payload


__all__ = ["ManualIdentityIntegrationAdapter"]
