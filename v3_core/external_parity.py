"""External integration parity models; no external clients or writes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IntegrationStatus(str, Enum):
    MATCHED = "MATCHED"
    NEEDS_VALIDATION = "NEEDS_VALIDATION"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class IntegrationMapping:
    source: str
    target: str
    mapping: str
    verification: str
    status: IntegrationStatus


@dataclass(frozen=True)
class ESPHomeParityModel:
    owner: str
    transport: str
    mappings: tuple[IntegrationMapping, ...]
    lease_owner: str
    availability: str


def esphome_parity_model() -> ESPHomeParityModel:
    mappings = (
        IntegrationMapping("ESPHome output_voltage/output_current", "RD6018 V/I", "setpoint telemetry", "fresh voltage/current readback", IntegrationStatus.NEEDS_VALIDATION),
        IntegrationMapping("ESPHome set_voltage_readback_v2", "V3 configured voltage", "readback sensor", "timestamp/freshness/match", IntegrationStatus.NEEDS_VALIDATION),
        IntegrationMapping("ESPHome set_current_readback_v2", "V3 configured current", "readback sensor", "timestamp/freshness/match", IntegrationStatus.NEEDS_VALIDATION),
        IntegrationMapping("ESPHome output_state_code_v2", "V3 output state", "state-code sensor", "fresh state confirmation", IntegrationStatus.NEEDS_VALIDATION),
        IntegrationMapping("ESPHome safety lease entities", "V3 lease observation", "armed/tripped/generation/remaining", "positive lease evidence", IntegrationStatus.NEEDS_VALIDATION),
    )
    return ESPHomeParityModel("ESPHome/edge dead-man", "ESPHome -> RD6018 connector", mappings, "ESPHome/edge dead-man", "must be proven on target")


@dataclass(frozen=True)
class HAIntegrationParityModel:
    telemetry_entities: tuple[str, ...]
    control_entities: tuple[str, ...]
    notification_role: str
    safety_owner: str
    physical_owner: str
    stale_policy: str
    availability_policy: str


def ha_integration_parity_model() -> HAIntegrationParityModel:
    return HAIntegrationParityModel(
        ("sensor.rd_6018_output_voltage", "sensor.rd_6018_output_current", "sensor.rd_6018_battery_voltage", "sensor.rd6018_rd_6018_temperature_internal_v2", "sensor.rd6018_rd_6018_output_state_code_v2"),
        ("switch.rd_6018_output", "number.rd_6018_output_voltage", "number.rd_6018_output_current"),
        "notification/presentation source",
        "V3 Safety Domain decides; HA does not",
        "V2/physical boundary; HA is transport/control source only",
        "stale is not success and requires safety policy",
        "unavailable is explicit, never silently last-known without provenance",
    )


class LeaseIntegrationScenario(str, Enum):
    NORMAL_RENEWAL = "normal_renewal"
    RENEWAL_TIMEOUT = "renewal_timeout"
    DUPLICATE_OWNER = "duplicate_owner"
    EXPIRY = "lease_expiry"
    RESTART_ACTIVE = "restart_active_lease"
    NETWORK_LOSS = "network_loss_during_lease"


@dataclass(frozen=True)
class LeaseIntegrationCase:
    scenario: LeaseIntegrationScenario
    expected_behavior: str
    safety_implication: str
    rollback: str


@dataclass(frozen=True)
class LeaseIntegrationParityReport:
    current_owner: str
    storage: str
    renewal: str
    expiry: str
    timeout_s: float
    fail_safe: str
    cases: tuple[LeaseIntegrationCase, ...]


def lease_integration_parity_report() -> LeaseIntegrationParityReport:
    cases = tuple(
        LeaseIntegrationCase(scenario, expected, implication, rollback)
        for scenario, expected, implication, rollback in (
            (LeaseIntegrationScenario.NORMAL_RENEWAL, "positive edge ACK required", "continue only with fresh proof", "retain current owner"),
            (LeaseIntegrationScenario.RENEWAL_TIMEOUT, "no assumed renewal", "dead-man remains final", "contain/re-authorize"),
            (LeaseIntegrationScenario.DUPLICATE_OWNER, "reject duplicate authority", "avoid competing lease writers", "keep current edge owner"),
            (LeaseIntegrationScenario.EXPIRY, "edge expiry containment", "physical safety remains local", "verified OFF or latch"),
            (LeaseIntegrationScenario.RESTART_ACTIVE, "no silent resume", "fresh lease and actuator verification", "operator reauthorization"),
            (LeaseIntegrationScenario.NETWORK_LOSS, "network loss cannot prove renewal", "edge dead-man protects locally", "verified recovery or containment"),
        )
    )
    return LeaseIntegrationParityReport("ESPHome/edge dead-man", "edge RAM lease state + published entities", "existing V2 EdgeSafetyLease", "local expiry to containment", 900.0, "local dead-man OFF/containment", cases)


@dataclass(frozen=True)
class TelemetryCandidate:
    source: str
    values: dict[str, Any]
    age_s: float
    confidence: float

    @property
    def fresh(self) -> bool:
        return self.age_s <= 20.0 and self.confidence > 0.0


@dataclass(frozen=True)
class TelemetryParityResult:
    selected_source: str
    selected: TelemetryCandidate | None
    conflicting: bool
    reason: str


class TelemetryParityValidationModel:
    def arbitrate(self, esp: TelemetryCandidate | None, ha: TelemetryCandidate | None, last_known: TelemetryCandidate | None = None) -> TelemetryParityResult:
        fresh = [candidate for candidate in (esp, ha) if candidate is not None and candidate.fresh]
        conflict = len(fresh) == 2 and fresh[0].values != fresh[1].values
        if esp is not None and esp.fresh:
            return TelemetryParityResult("ESP_DIRECT", esp, conflict, "esp_fresh_conflict" if conflict else "esp_fresh")
        if ha is not None and ha.fresh:
            return TelemetryParityResult("HA", ha, False, "ha_fresh")
        if last_known is not None:
            return TelemetryParityResult("LAST_KNOWN", last_known, False, "no_fresh_source")
        return TelemetryParityResult("UNKNOWN", None, False, "no_telemetry")


class ExternalReadbackStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    TIMEOUT = "TIMEOUT"
    MISMATCH = "MISMATCH"


class ExternalReadbackValidationModel:
    def verify(self, *, command_accepted: bool, physical_changed: bool | None, telemetry_confirms: bool | None, timed_out: bool = False) -> ExternalReadbackStatus:
        if timed_out:
            return ExternalReadbackStatus.TIMEOUT
        if not command_accepted or physical_changed is False or telemetry_confirms is False:
            return ExternalReadbackStatus.MISMATCH
        if physical_changed is None or telemetry_confirms is None:
            return ExternalReadbackStatus.UNVERIFIED
        return ExternalReadbackStatus.VERIFIED


@dataclass(frozen=True)
class ExternalFailureCase:
    category: str
    scenario: str
    detection: str
    owner: str
    decision: str
    containment: str
    verification: str
    recovery: str


def external_failure_matrix() -> tuple[ExternalFailureCase, ...]:
    return tuple(
        ExternalFailureCase(category, scenario, detection, "V3 Safety Domain", decision, containment, verification, recovery)
        for category, scenario, detection, decision, containment, verification, recovery in (
            ("transport", "unavailable", "transport status", "defer/contain", "no command assumed", "explicit unavailable", "retry after fresh availability"),
            ("transport", "timeout", "timeout clock", "contain if policy threshold", "rollback intent", "timeout result", "operator-visible retry"),
            ("ESPHome", "offline", "availability", "lease not renewed", "edge dead-man", "edge state", "fresh lease proof"),
            ("ESPHome", "stale/wrong state", "readback freshness", "contain", "verified OFF/latch", "fresh state", "manual validation"),
            ("HA", "unavailable/stale", "HA source freshness", "arbitrate/fail safe", "no unsafe assumption", "ESP/last-known provenance", "source recovery"),
            ("lease", "expired/duplicated/lost", "lease observation", "reject authority/contain", "dead-man final", "edge readback", "operator reauthorization"),
            ("telemetry", "missing/conflicting", "source arbitration", "contain or unknown", "no unsafe decision", "fresh source", "source reconciliation"),
            ("readback", "mismatch/delayed", "verification layer", "rollback/contain", "verified OFF/latch", "matching fresh observation", "reissue only under policy"),
        )
    )


__all__ = [
    "IntegrationStatus", "IntegrationMapping", "ESPHomeParityModel", "esphome_parity_model",
    "HAIntegrationParityModel", "ha_integration_parity_model", "LeaseIntegrationScenario",
    "LeaseIntegrationCase", "LeaseIntegrationParityReport", "lease_integration_parity_report",
    "TelemetryCandidate", "TelemetryParityResult", "TelemetryParityValidationModel",
    "ExternalReadbackStatus", "ExternalReadbackValidationModel", "ExternalFailureCase", "external_failure_matrix",
]
