"""Pure persistence boundary contracts for Phase 8.5.

The reference provider is in-memory and exists only for contract/shadow tests.
No filesystem, database, transport, domain decision, or actuator operation is
performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import uuid4


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


class PersistenceKind(str, Enum):
    DOMAIN_STATE = "domain_state"
    HISTORICAL_DATA = "historical_data"
    SHADOW_EVIDENCE = "shadow_evidence"


class PersistenceError(ValueError):
    pass


class RestoreRejected(PersistenceError):
    pass


@dataclass(frozen=True)
class StateSnapshot:
    """Validated candidate state; it is not an instruction to resume runtime."""

    snapshot_id: str
    state_type: str
    owner: str
    session_id: str | None
    schema_version: int
    captured_at: datetime
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.state_type.strip() or not self.owner.strip():
            raise PersistenceError("snapshot identity and owner are required")
        if self.schema_version < 1:
            raise PersistenceError("schema_version must be positive")
        if not isinstance(self.payload, Mapping):
            raise TypeError("snapshot payload must be a mapping")
        object.__setattr__(self, "payload", _freeze(self.payload))

    @classmethod
    def new(
        cls,
        *,
        state_type: str,
        owner: str,
        payload: Mapping[str, Any],
        session_id: str | None = None,
        schema_version: int = 1,
        captured_at: datetime | None = None,
    ) -> "StateSnapshot":
        return cls(
            snapshot_id=uuid4().hex,
            state_type=state_type,
            owner=owner,
            session_id=session_id,
            schema_version=schema_version,
            captured_at=captured_at or datetime.now(timezone.utc),
            payload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "state_type": self.state_type,
            "owner": self.owner,
            "session_id": self.session_id,
            "schema_version": self.schema_version,
            "captured_at": self.captured_at.isoformat(),
            "payload": _plain(self.payload),
        }


@dataclass(frozen=True)
class PersistenceRecord:
    """Envelope stored by a persistence provider."""

    record_id: str
    kind: PersistenceKind
    snapshot: StateSnapshot

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise PersistenceError("record_id is required")
        if not isinstance(self.kind, PersistenceKind):
            raise TypeError("kind must be PersistenceKind")
        if not isinstance(self.snapshot, StateSnapshot):
            raise TypeError("snapshot must be StateSnapshot")


@dataclass(frozen=True)
class RestoreCandidate:
    """Validated domain candidate awaiting fresh runtime verification."""

    candidate_id: str
    snapshot: StateSnapshot
    requires_fresh_verification: bool = True
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise PersistenceError("candidate_id is required")
        if not isinstance(self.snapshot, StateSnapshot):
            raise TypeError("candidate snapshot is required")
        if not self.requires_fresh_verification:
            raise RestoreRejected("restore candidates require fresh verification")
        if self.verified:
            raise RestoreRejected("persistence cannot mark a candidate freshly verified")


class PersistenceProvider(Protocol):
    """Persistence boundary; it has no restore authority or infrastructure client."""

    def save(self, record: PersistenceRecord) -> None: ...

    def load(self, record_id: str) -> PersistenceRecord | None: ...

    def restore_candidate(self, record: PersistenceRecord) -> RestoreCandidate: ...


_DOMAIN_OWNERS = frozenset({"Session Domain", "Charge Domain", "Strategy Domain"})
_HISTORY_OWNERS = frozenset({"Telemetry History", "Diagnostics Domain", "Shadow Evidence"})
_FORBIDDEN_STATE_MARKERS = frozenset({"containment", "lease", "actuator", "output", "safety"})


class InMemoryPersistenceProvider:
    """Non-production reference provider used to test the boundary."""

    def __init__(self) -> None:
        self._records: dict[str, PersistenceRecord] = {}

    def save(self, record: PersistenceRecord) -> None:
        if not isinstance(record, PersistenceRecord):
            raise TypeError("PersistenceRecord is required")
        if record.kind is PersistenceKind.DOMAIN_STATE and record.snapshot.owner not in _DOMAIN_OWNERS:
            raise PersistenceError("domain state owner is not approved")
        if record.kind in {PersistenceKind.HISTORICAL_DATA, PersistenceKind.SHADOW_EVIDENCE} and record.snapshot.owner not in _HISTORY_OWNERS:
            raise PersistenceError("historical data owner is not approved")
        self._records[record.record_id] = record

    def load(self, record_id: str) -> PersistenceRecord | None:
        return self._records.get(record_id)

    def restore_candidate(self, record: PersistenceRecord) -> RestoreCandidate:
        if record.kind is not PersistenceKind.DOMAIN_STATE:
            raise RestoreRejected("historical data is not a domain restore candidate")
        state_marker = record.snapshot.state_type.lower()
        if any(marker in state_marker for marker in _FORBIDDEN_STATE_MARKERS):
            raise RestoreRejected("safety, lease and actuator state cannot be restored directly")
        if record.snapshot.owner not in _DOMAIN_OWNERS:
            raise RestoreRejected("restore owner is not a domain owner")
        return RestoreCandidate(uuid4().hex, record.snapshot)


__all__ = [
    "PersistenceKind", "PersistenceError", "RestoreRejected", "StateSnapshot",
    "PersistenceRecord", "RestoreCandidate", "PersistenceProvider",
    "InMemoryPersistenceProvider",
]
