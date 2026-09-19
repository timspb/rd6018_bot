"""Read-only evidence bundle for the first V2-owned Manual identity chain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from application.shadow_evidence_chain import EvidenceChainResult, ShadowEvidenceChainValidator
from v3_core.canonical_events import CanonicalChargeEvent
from v3_core.shadow_runtime_evidence import ReplayResult, ShadowEvidenceBundle, ShadowReplayEngine


class ManualIdentityEvidenceStatus(str, Enum):
    CAPTURED = "MANUAL_IDENTITY_EVIDENCE_CAPTURED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ManualIdentityEvidenceBundle:
    status: ManualIdentityEvidenceStatus
    session_id: str | None
    trace_id: str | None
    events: tuple[CanonicalChargeEvent, ...]
    telemetry: tuple[Mapping[str, Any], ...]
    rd_readback: tuple[Mapping[str, Any], ...]
    esphome_state: tuple[Mapping[str, Any], ...]
    ha_state: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[Mapping[str, Any], ...]
    chain_result: EvidenceChainResult
    replay_result: ReplayResult | None
    ui_timeline_valid: bool


class ManualIdentityEvidenceCollector:
    """Validate supplied observations only; it has no source clients or writers."""

    def __init__(self, validator: ShadowEvidenceChainValidator | None = None) -> None:
        self._validator = validator or ShadowEvidenceChainValidator()

    def capture(self, *, events: Iterable[CanonicalChargeEvent], session_id: str | None, telemetry: Iterable[Mapping[str, Any]] = (), rd_readback: Iterable[Mapping[str, Any]] = (), esphome_state: Iterable[Mapping[str, Any]] = (), ha_state: Iterable[Mapping[str, Any]] = (), diagnostics: Iterable[Mapping[str, Any]] = (), ui_timeline_valid: bool = True, evidence_id: str = "manual-observation", observation_id: str = "manual-observation", created_at: float = 1.0) -> ManualIdentityEvidenceBundle:
        captured = tuple(events)
        if not session_id or not captured:
            result = self._validator.validate(captured, session_id=session_id or "")
            return ManualIdentityEvidenceBundle(ManualIdentityEvidenceStatus.BLOCKED, session_id, captured[0].trace_id if captured else None, captured, tuple(telemetry), tuple(rd_readback), tuple(esphome_state), tuple(ha_state), tuple(diagnostics), result, None, ui_timeline_valid)
        result = self._validator.validate(captured, session_id=session_id)
        status = ManualIdentityEvidenceStatus.CAPTURED if result.complete and ui_timeline_valid else ManualIdentityEvidenceStatus.PARTIAL
        trace_ids = {event.trace_id for event in captured}
        trace_id = next(iter(trace_ids), None) if len(trace_ids) == 1 else None
        replay = None
        if trace_id:
            bundle = ShadowEvidenceBundle(evidence_id, observation_id, session_id, trace_id, created_at, events=captured, current_phase=captured[-1].phase_after, session_state="observed")
            replay = ShadowReplayEngine().replay(bundle)
        return ManualIdentityEvidenceBundle(status, session_id, trace_id, captured, tuple(telemetry), tuple(rd_readback), tuple(esphome_state), tuple(ha_state), tuple(diagnostics), result, replay, ui_timeline_valid)


__all__ = ["ManualIdentityEvidenceStatus", "ManualIdentityEvidenceBundle", "ManualIdentityEvidenceCollector"]
