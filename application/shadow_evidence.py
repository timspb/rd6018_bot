"""Analytical V2/V3 shadow evidence store for Phase 10.1.

This is a separate ``shadow_evidence`` persistence namespace. Records are
historical evidence only and can never become runtime restore candidates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .diagnostics_domain import DiagnosticEvent
from .divergence_explanation import DivergenceAnalysis
from .persistence_boundary import (
    InMemoryPersistenceProvider,
    PersistenceKind,
    PersistenceRecord,
    RestoreRejected,
    StateSnapshot,
)
from .production_shadow_observer import ShadowObservationRecord
from .v2_v3_comparison import ComparisonResult, DecisionSnapshot


def _plain(value: Any) -> Any:
    if hasattr(value, "value") and not isinstance(value, (str, bytes, dict, list, tuple)):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {name: _plain(getattr(value, name)) for name in value.__dataclass_fields__}
    return value


def _hash_snapshot(snapshot: Any) -> str:
    payload = json.dumps(_plain(snapshot), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ShadowEvidenceRecord:
    trace_id: str
    timestamp: datetime
    input_snapshot_hash: str
    v2_decision: DecisionSnapshot
    v3_decision: DecisionSnapshot | None
    comparison: ComparisonResult
    divergence_explanation: DivergenceAnalysis
    diagnostics_references: tuple[str, ...]
    namespace: str = "shadow_evidence"

    def __post_init__(self) -> None:
        if not self.trace_id.strip() or not self.input_snapshot_hash.strip():
            raise ValueError("trace_id and input_snapshot_hash are required")
        if self.namespace != "shadow_evidence":
            raise ValueError("shadow evidence namespace is fixed")


class ShadowEvidenceStore:
    """Store and query shadow evidence; never restore it into runtime."""

    NAMESPACE = "shadow_evidence"

    def __init__(self, persistence: InMemoryPersistenceProvider | None = None) -> None:
        self._persistence = persistence or InMemoryPersistenceProvider()
        self._records: list[ShadowEvidenceRecord] = []

    @property
    def records(self) -> tuple[ShadowEvidenceRecord, ...]:
        return tuple(self._records)

    def save_observation(self, observation: ShadowObservationRecord) -> ShadowEvidenceRecord:
        if not isinstance(observation, ShadowObservationRecord):
            raise TypeError("ShadowObservationRecord is required")
        evidence = ShadowEvidenceRecord(
            trace_id=observation.trace_id,
            timestamp=datetime.now(timezone.utc),
            input_snapshot_hash=_hash_snapshot(observation.input_snapshot),
            v2_decision=observation.v2_decision,
            v3_decision=observation.v3_decision,
            comparison=observation.comparison,
            divergence_explanation=observation.explanation,
            diagnostics_references=(observation.diagnostic.event_id,),
        )
        payload = _plain(evidence)
        snapshot = StateSnapshot.new(
            state_type="shadow_evidence_record",
            owner="Shadow Evidence",
            session_id=None,
            payload=payload,
        )
        self._persistence.save(PersistenceRecord(evidence.trace_id + ":" + evidence.input_snapshot_hash[:12], PersistenceKind.SHADOW_EVIDENCE, snapshot))
        self._records.append(evidence)
        return evidence

    def query_history(self, *, trace_id: str | None = None, limit: int | None = None) -> tuple[ShadowEvidenceRecord, ...]:
        records = tuple(record for record in self._records if trace_id is None or record.trace_id == trace_id)
        if limit is None:
            return records
        if limit < 0:
            raise ValueError("limit must not be negative")
        return records[-limit:] if limit else ()

    def restore_candidate(self, *_args: Any, **_kwargs: Any) -> None:
        raise RestoreRejected("shadow evidence is analytical history, not runtime restore state")


__all__ = ["ShadowEvidenceRecord", "ShadowEvidenceStore"]
