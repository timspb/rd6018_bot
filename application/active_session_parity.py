"""Observer-only parity model for an already-active Manual session."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ActiveSessionIdentityStatus(str, Enum):
    LEGACY_NO_IDENTITY = "LEGACY_NO_IDENTITY"
    IDENTITY_PRESENT = "IDENTITY_PRESENT"


class ActiveSessionParityStatus(str, Enum):
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ActiveSessionObservation:
    profile: str | None
    phase: str | None
    state: str | None
    telemetry: Mapping[str, Any]
    confidence: str
    identity_status: ActiveSessionIdentityStatus
    session_id: str | None = None
    trace_id: str | None = None


@dataclass(frozen=True)
class ActiveSessionParityEvidence:
    observation: ActiveSessionObservation
    v2_state: Mapping[str, Any]
    v3_state: Mapping[str, Any]
    comparison: ActiveSessionParityStatus
    reason: str
    diagnostics: tuple[Mapping[str, Any], ...] = ()
    ui_current_session_only: bool = True
    fake_start_emitted: bool = False


class ActiveSessionParityObserver:
    """Reconstruct current state from supplied snapshots; never creates lifecycle events."""

    def ingest(self, *, persisted: Mapping[str, Any], telemetry: Mapping[str, Any], rd: Mapping[str, Any] | None = None, esphome: Mapping[str, Any] | None = None, ha: Mapping[str, Any] | None = None) -> ActiveSessionObservation:
        rd = rd or {}
        esphome = esphome or {}
        ha = ha or {}
        request = persisted.get("request") if isinstance(persisted.get("request"), Mapping) else {}
        profile = persisted.get("profile") or persisted.get("battery_id") or request.get("battery_id") or request.get("profile")
        phase = persisted.get("phase") or persisted.get("stage") or request.get("stage") or rd.get("phase") or esphome.get("phase") or ha.get("phase")
        state = persisted.get("state") or rd.get("state") or esphome.get("state") or ha.get("state")
        sources = (telemetry, rd, esphome, ha)
        merged = {key: value for source in sources for key, value in source.items() if value is not None}
        identity = persisted.get("session_identity") if isinstance(persisted.get("session_identity"), Mapping) else {}
        source_count = sum(bool(source) for source in sources)
        confidence = "HIGH" if source_count >= 3 else "MEDIUM" if source_count == 2 else "LOW"
        return ActiveSessionObservation(profile, phase, state, merged, confidence, ActiveSessionIdentityStatus.IDENTITY_PRESENT if identity.get("session_id") and identity.get("trace_id") else ActiveSessionIdentityStatus.LEGACY_NO_IDENTITY, identity.get("session_id"), identity.get("trace_id"))

    def compare(self, observation: ActiveSessionObservation, *, v2_state: Mapping[str, Any], v3_state: Mapping[str, Any], diagnostics: tuple[Mapping[str, Any], ...] = ()) -> ActiveSessionParityEvidence:
        keys = ("profile", "phase", "state")
        missing = [key for key in keys if v2_state.get(key) is None or v3_state.get(key) is None]
        if missing:
            status = ActiveSessionParityStatus.UNKNOWN
            reason = "missing comparison fields: " + ", ".join(missing)
        elif all(v2_state[key] == v3_state[key] for key in keys):
            status = ActiveSessionParityStatus.MATCH
            reason = "active state, phase and profile agree"
        else:
            status = ActiveSessionParityStatus.EXPECTED_DIFFERENCE
            reason = "reconstructed V3 view differs from current V2 view"
        return ActiveSessionParityEvidence(observation, dict(v2_state), dict(v3_state), status, reason, diagnostics, True, False)


__all__ = ["ActiveSessionIdentityStatus", "ActiveSessionParityStatus", "ActiveSessionObservation", "ActiveSessionParityEvidence", "ActiveSessionParityObserver"]
