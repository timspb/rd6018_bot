"""Read-only ownership provenance diagnostics.

This module deliberately has no actuator or authority dependencies.  It converts
already-observed manager/live evidence into a diagnostic value; it never calls a
control method and never changes application state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional


class OwnershipMode(str, Enum):
    PB_MANAGED = "PB_MANAGED"
    HANDS_OFF = "HANDS_OFF"
    AUTONOMOUS = "AUTONOMOUS"


class OutputState(str, Enum):
    ON = "ON"
    OFF = "OFF"
    UNKNOWN = "UNKNOWN"


class OwnershipProvenance(str, Enum):
    BOT_MANAGED = "BOT_MANAGED"
    FOREIGN_OBSERVED = "FOREIGN_OBSERVED"
    AUTONOMOUS = "AUTONOMOUS"
    UNKNOWN = "UNKNOWN"


class EvidenceConfidence(str, Enum):
    VERIFIED = "VERIFIED"
    OBSERVED = "OBSERVED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class OwnershipSnapshot:
    """A point-in-time diagnostic view, not an authority decision."""

    mode: OwnershipMode
    output: OutputState
    provenance: OwnershipProvenance
    confidence: EvidenceConfidence


def _parse_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1"}:
            return True
        if normalized in {"off", "false", "0"}:
            return False
    return None


def _fresh_edge_evidence(live: Mapping[str, Any]) -> bool:
    metadata = live.get("_meta")
    if not isinstance(metadata, Mapping):
        return False
    edge = metadata.get("autonomous_mode")
    if not isinstance(edge, Mapping):
        return False
    status = str(edge.get("status") or "").strip().lower()
    return status not in {"", "unknown", "unavailable", "stale"}


def _manager_mode(manager: Any) -> OwnershipMode:
    if bool(getattr(manager, "edge_autonomous", False)):
        return OwnershipMode.AUTONOMOUS
    if bool(getattr(manager, "hands_off", False)):
        return OwnershipMode.HANDS_OFF
    return OwnershipMode.PB_MANAGED


def build_ownership_snapshot(
    live: Any,
    manager: Any = None,
    *,
    session_valid: Optional[bool] = None,
    lease_valid: Optional[bool] = None,
    edge_state_fresh: Optional[bool] = None,
    startup_recovery: bool = False,
) -> OwnershipSnapshot:
    """Build a diagnostic snapshot from existing observations only.

    ``session_valid`` and ``lease_valid`` are optional read-only evidence supplied
    by the caller.  They are not recomputed here and are never used to authorize
    an actuator operation.
    """

    if not isinstance(live, Mapping):
        return OwnershipSnapshot(
            _manager_mode(manager), OutputState.UNKNOWN,
            OwnershipProvenance.UNKNOWN, EvidenceConfidence.UNKNOWN,
        )

    output_value = _parse_bool(live.get("switch"))
    output = OutputState.ON if output_value is True else (
        OutputState.OFF if output_value is False else OutputState.UNKNOWN
    )
    explicit_autonomous = _parse_bool(live.get("autonomous_mode"))
    fresh_edge = _fresh_edge_evidence(live) if edge_state_fresh is None else bool(edge_state_fresh)
    mode = (
        OwnershipMode.AUTONOMOUS if explicit_autonomous is True and fresh_edge
        else _manager_mode(manager)
    )

    if explicit_autonomous is True and fresh_edge:
        return OwnershipSnapshot(mode, output, OwnershipProvenance.AUTONOMOUS, EvidenceConfidence.VERIFIED)

    controller = getattr(getattr(manager, "app", None), "charge_controller", None)
    manual = getattr(getattr(manager, "app", None), "manual_session_manager", None)
    managed_active = bool(
        getattr(controller, "is_active", False) or getattr(manual, "is_active", False)
    )
    if managed_active and output is OutputState.ON:
        verified = session_valid is not False and lease_valid is not False
        return OwnershipSnapshot(
            mode, output, OwnershipProvenance.BOT_MANAGED,
            EvidenceConfidence.VERIFIED if verified else EvidenceConfidence.OBSERVED,
        )

    if output is OutputState.ON and startup_recovery:
        return OwnershipSnapshot(
            mode, output, OwnershipProvenance.UNKNOWN,
            EvidenceConfidence.UNKNOWN,
        )

    if output is OutputState.ON:
        return OwnershipSnapshot(
            mode, output, OwnershipProvenance.FOREIGN_OBSERVED,
            EvidenceConfidence.OBSERVED,
        )

    return OwnershipSnapshot(
        mode, output, OwnershipProvenance.UNKNOWN, EvidenceConfidence.UNKNOWN,
    )
