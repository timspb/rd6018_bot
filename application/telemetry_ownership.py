"""Staged V2/V3 telemetry ownership coordinator for Phase 11.0."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .telemetry_authority import TelemetryArbitrator, TelemetrySnapshot, TelemetrySource


class TelemetryOwnershipState(str, Enum):
    V2_PRIMARY = "V2_PRIMARY"
    V3_STAGED = "V3_STAGED"
    V2_ROLLBACK = "V2_ROLLBACK"


class TelemetryParityState(str, Enum):
    EQUAL = "equal"
    DIFFERENT = "different"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TelemetryParity:
    state: TelemetryParityState
    differences: dict[str, Any]


@dataclass(frozen=True)
class TelemetryOwnershipView:
    trace_id: str
    state: TelemetryOwnershipState
    snapshot: TelemetrySnapshot
    v2_snapshot: TelemetrySnapshot | None
    parity: TelemetryParity
    provenance: str
    observed_at: datetime


class TelemetryOwnershipCoordinator:
    """Select V3 telemetry authority while preserving V2 rollback."""

    def __init__(self, arbitrator: TelemetryArbitrator | None = None) -> None:
        self.arbitrator = arbitrator or TelemetryArbitrator()
        self.state = TelemetryOwnershipState.V2_PRIMARY
        self._v2_snapshot: TelemetrySnapshot | None = None
        self._canonical: TelemetrySnapshot | None = None
        self._shadow_evidence: list[TelemetryOwnershipView] = []

    @property
    def shadow_evidence(self) -> tuple[TelemetryOwnershipView, ...]:
        return tuple(self._shadow_evidence)

    def stage(
        self,
        *,
        trace_id: str,
        v2_snapshot: TelemetrySnapshot | None,
        esp_direct: TelemetrySnapshot | None,
        ha: TelemetrySnapshot | None,
        now: datetime | None = None,
    ) -> TelemetryOwnershipView:
        if not trace_id.strip():
            raise ValueError("trace_id is required")
        current = now or datetime.now(timezone.utc)
        self._v2_snapshot = v2_snapshot
        selected = self.arbitrator.select(esp_direct=esp_direct, ha=ha, now=current)
        self._canonical = selected
        self.state = TelemetryOwnershipState.V3_STAGED
        parity = self._compare(v2_snapshot, selected)
        view = TelemetryOwnershipView(trace_id, self.state, selected, v2_snapshot, parity, selected.source.value, current)
        self._shadow_evidence.append(view)
        return view

    def canonical(self) -> TelemetrySnapshot | None:
        return self._v2_snapshot if self.state is not TelemetryOwnershipState.V3_STAGED else self._canonical

    def rollback_to_v2(self, *, trace_id: str, now: datetime | None = None) -> TelemetryOwnershipView:
        if not trace_id.strip():
            raise ValueError("trace_id is required")
        current = now or datetime.now(timezone.utc)
        self.state = TelemetryOwnershipState.V2_ROLLBACK
        snapshot = self._v2_snapshot or self._unknown(current)
        parity = self._compare(snapshot, snapshot)
        view = TelemetryOwnershipView(trace_id, self.state, snapshot, self._v2_snapshot, parity, "V2 telemetry rollback", current)
        self._shadow_evidence.append(view)
        return view

    @staticmethod
    def _compare(v2: TelemetrySnapshot | None, v3: TelemetrySnapshot) -> TelemetryParity:
        if v2 is None or v3.source is TelemetrySource.UNKNOWN:
            return TelemetryParity(TelemetryParityState.UNKNOWN, {})
        differences: dict[str, Any] = {}
        for field in ("voltage", "current", "power", "temperature", "output_state"):
            left, right = getattr(v2, field), getattr(v3, field)
            if left != right:
                differences[field] = {"v2": left, "v3": right}
        return TelemetryParity(
            TelemetryParityState.EQUAL if not differences else TelemetryParityState.DIFFERENT,
            differences,
        )

    @staticmethod
    def _unknown(now: datetime) -> TelemetrySnapshot:
        return TelemetrySnapshot(None, None, None, None, None, now, now, 0.0, False, TelemetrySource.UNKNOWN, 0.0)


__all__ = ["TelemetryOwnershipState", "TelemetryParityState", "TelemetryParity", "TelemetryOwnershipView", "TelemetryOwnershipCoordinator"]
