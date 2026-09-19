"""Final safety ownership map as data; it does not replace V2 writers."""

from __future__ import annotations

from dataclasses import dataclass

from .safety_boundary import SAFETY_DECISION_OWNER


@dataclass(frozen=True)
class SafetyOwnershipRecord:
    trigger: str
    detection: tuple[str, ...]
    decision_owner: str
    execution_owner: str
    physical_boundary: str
    migration_state: str


_RECORDS = (
    SafetyOwnershipRecord("watchdog", ("runtime watchdog", "soft watchdog"), SAFETY_DECISION_OWNER, "V2 runtime/SafeOutput", "SafeOutput + edge dead-man", "MAPPED"),
    SafetyOwnershipRecord("telemetry_loss", ("HA telemetry", "ESP direct telemetry"), SAFETY_DECISION_OWNER, "V2 runtime/SafeOutput", "SafeOutput", "MAPPED"),
    SafetyOwnershipRecord("lease_loss", ("ESPHome lease", "edge lease"), SAFETY_DECISION_OWNER, "ESPHome/edge dead-man", "ESPHome local dead-man", "MAPPED"),
    SafetyOwnershipRecord("manual_stop", ("Telegram/manual operator" ,), SAFETY_DECISION_OWNER, "V2 manual/SafeOutput", "SafeOutput", "MAPPED"),
    SafetyOwnershipRecord("emergency_stop", ("runtime_safety", "runtime_safety_v2", "runtime_safety_strict"), SAFETY_DECISION_OWNER, "V2 safety/SafeOutput", "SafeOutput", "MAPPED"),
    SafetyOwnershipRecord("readback_failure", ("readback verifier", "transport"), SAFETY_DECISION_OWNER, "V2 SafeOutput", "SafeOutput + verified OFF", "MAPPED"),
)


def safety_ownership_map() -> tuple[SafetyOwnershipRecord, ...]:
    return _RECORDS


def active_execution_writers() -> tuple[str, ...]:
    return tuple(sorted({record.execution_owner for record in _RECORDS}))


__all__ = ["SafetyOwnershipRecord", "safety_ownership_map", "active_execution_writers"]
