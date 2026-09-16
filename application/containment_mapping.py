"""Observation-only mapping from legacy containment paths to Phase 3 results.

The mapping is descriptive. It does not call runtime safety, controllers, HA,
the lease, or any physical adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from .containment_result import ContainmentResult, ContainmentVerificationState


@dataclass(frozen=True)
class ContainmentPathMapping:
    """Static description of one existing containment path."""

    path_id: str
    source: str
    trigger: str
    current_action: str
    current_verification: str
    requested_action: str
    physical_owner: str
    verification_state: ContainmentVerificationState

    def to_result(self, *, trace_id: str, event_id: str | None = None) -> ContainmentResult:
        """Create an observation result without executing the described action."""
        result = ContainmentResult(
            event_id=event_id or f"observation:{self.path_id}",
            trace_id=trace_id,
            source=self.source,
            trigger=self.trigger,
            requested_action=self.requested_action,
            physical_owner=self.physical_owner,
            verification_state=self.verification_state,
        )
        return result


_KNOWN_MAPPINGS = (
    ContainmentPathMapping(
        "runtime-watchdog-ha-timeout",
        "runtime_watchdog",
        "HA telemetry/controller update timeout",
        "_hard_stop_charge and emergency stop path",
        "HA live/readback plus controller/session state",
        "verified_output_off",
        "v2_runtime_safety_output",
        ContainmentVerificationState.REQUESTED,
    ),
    ContainmentPathMapping(
        "runtime-watchdog-high-voltage",
        "runtime_watchdog",
        "high voltage watchdog threshold",
        "_hard_stop_charge and emergency HV disconnect marker",
        "HA live/readback",
        "verified_output_off",
        "v2_runtime_safety_output",
        ContainmentVerificationState.REQUESTED,
    ),
    ContainmentPathMapping(
        "runtime-safety-fail-closed",
        "runtime_safety",
        "invalid telemetry/readback/command precondition",
        "fail closed; guarded OFF when required",
        "raw live state and output evidence",
        "fail_closed",
        "runtime_safety_guard",
        ContainmentVerificationState.UNKNOWN,
    ),
    ContainmentPathMapping(
        "runtime-safety-v2-hardware-trip",
        "runtime_safety_v2",
        "hardware OVP/OCP or temperature/integrity fault",
        "ensure OFF and retire/latch session",
        "output/readback and durable latch where applicable",
        "verified_output_off_and_contain",
        "runtime_safety_v2",
        ContainmentVerificationState.UNKNOWN,
    ),
    ContainmentPathMapping(
        "runtime-safety-strict-lease-failure",
        "runtime_safety_strict",
        "edge lease renewal or strict runtime failure",
        "fail closed and enter OFF/lease handling",
        "HA readback plus lease acknowledgement",
        "verified_output_off_and_lease_containment",
        "runtime_safety_strict_and_edge_lease",
        ContainmentVerificationState.UNKNOWN,
    ),
    ContainmentPathMapping(
        "safe-output-transaction-failure",
        "safe_output_coordinator",
        "transactional enable/disable or post-enable failure",
        "force OFF",
        "adapter result and positive output readback",
        "force_verified_output_off",
        "safe_output_coordinator",
        ContainmentVerificationState.UNKNOWN,
    ),
    ContainmentPathMapping(
        "edge-lease-failure",
        "edge_safety_lease",
        "renewal/disarm acknowledgement failure",
        "preserve fail-safe lease state",
        "generation, armed/tripped state and fresh edge readback",
        "preserve_edge_containment",
        "edge_safety_lease",
        ContainmentVerificationState.OFF_UNCONFIRMED,
    ),
    ContainmentPathMapping(
        "esphome-dead-man-expiry",
        "esphome_dead_man",
        "local lease/watchdog expiry",
        "local Output OFF",
        "edge-local state/readback",
        "local_output_off",
        "esphome_edge",
        ContainmentVerificationState.UNKNOWN,
    ),
    ContainmentPathMapping(
        "manual-stop",
        "manual_runtime",
        "operator stop or manual session failure",
        "stop session and request Output OFF",
        "manual session state and output readback",
        "stop_and_verified_output_off",
        "manual_runtime_v2_safety_output",
        ContainmentVerificationState.REQUESTED,
    ),
    ContainmentPathMapping(
        "emergency-stop",
        "operator_emergency_stop",
        "explicit emergency stop",
        "hard stop/managed stop route",
        "positive output OFF evidence",
        "emergency_verified_output_off",
        "v2_safety_output",
        ContainmentVerificationState.REQUESTED,
    ),
)


def known_containment_mappings() -> tuple[ContainmentPathMapping, ...]:
    """Return the immutable inventory of currently known containment paths."""
    return _KNOWN_MAPPINGS


def observe_containment(path_id: str, *, trace_id: str) -> ContainmentResult:
    """Map a known path to a result; this function has no side effects."""
    for mapping in _KNOWN_MAPPINGS:
        if mapping.path_id == path_id:
            return mapping.to_result(trace_id=trace_id)
    raise KeyError(f"unknown containment path: {path_id}")
