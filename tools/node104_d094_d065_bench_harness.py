"""Offline-first D065 acceptance driver. Live hardware execution is disabled."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
from typing import Protocol


LEASE_TTL_S = 900
RENEWAL_S = 300
MAX_SETPOINT_V = 15.5
FRESHNESS_S = 8.0


class Action(str, Enum):
    RENEW = "renew"
    DISARM = "disarm"
    ENTER_AUTONOMOUS = "enter_autonomous"
    EXIT_AUTONOMOUS = "exit_autonomous"


class HarnessError(RuntimeError):
    pass


class LiveExecutionDisabled(HarnessError):
    pass


@dataclass(frozen=True)
class Evidence:
    # Independent HA and native ESP R18/V/I observations. Native measurements
    # must specifically have come from SensorState; NumberState is a setpoint.
    ha_r18: int = 0
    ha_voltage: float = 0.0
    ha_current: float = 0.0
    ha_age_s: float = 0.0
    native_r18: int = 0
    native_voltage: float = 0.0
    native_current: float = 0.0
    native_measurement_type: str = "SensorState"
    native_age_s: float = 0.0
    armed: bool = False
    remaining_s: float = 0.0
    generation: int = 0
    autonomous: bool = False
    tripped: bool = False
    boot_quarantine: bool = False
    authority_conflict: bool = False
    lease_ttl_s: int = LEASE_TTL_S
    setpoint_v: float = 13.6
    owner_count: int = 1
    handoff_locked: bool = True


class EdgeActionGateway(Protocol):
    """One injected action boundary; no HA, ESPHome or button client here."""
    def invoke(self, action: Action, evidence: Evidence) -> Evidence: ...


class OfflineNode:
    """Isolated stateful ESP contract model, never connected to an application."""
    def __init__(self, **faults: object):
        self.faults = faults
        self.state = Evidence()
        self.calls: list[Action] = []

    def invoke(self, action: Action, evidence: Evidence) -> Evidence:
        if not isinstance(action, Action):
            raise HarnessError("only modeled actions are accepted")
        self.calls.append(action)
        s = self.state
        if self.faults.get("missing_ack") or self.faults.get("failed_ack"):
            raise HarnessError("simulated command acknowledgement missing/failed")
        if self.faults.get("timeout") or self.faults.get("cancelled"):
            raise HarnessError("simulated action timeout/cancellation; fail closed")
        if action is Action.RENEW:
            if (s.autonomous or s.tripped or s.boot_quarantine or
                    evidence.lease_ttl_s != LEASE_TTL_S or
                    evidence.ha_r18 != 0 or evidence.native_r18 != 0 or
                    evidence.native_measurement_type != "SensorState"):
                return s
            s = replace(s, armed=True, remaining_s=899, generation=s.generation + 1)
            if self.faults.get("renew_unconfirmed"):
                s = replace(s, armed=False, remaining_s=0)
        elif action is Action.DISARM:
            if evidence.native_r18 != 0 or evidence.ha_r18 != 0 or s.autonomous:
                return s
            s = replace(s, armed=False, remaining_s=0, tripped=False)
            if self.faults.get("disarm_remaining"):
                s = replace(s, remaining_s=1)
        elif action is Action.ENTER_AUTONOMOUS:
            if (s.armed or s.autonomous or s.tripped or s.boot_quarantine or
                    evidence.native_r18 != 0 or evidence.ha_r18 != 0):
                return s
            s = replace(s, autonomous=True, generation=s.generation + 1)
        elif action is Action.EXIT_AUTONOMOUS:
            if not s.autonomous or s.armed or evidence.native_r18 != 0 or evidence.ha_r18 != 0:
                return s
            s = replace(s, autonomous=False, generation=s.generation + 1)
        self.state = s
        # Fault injection models dangerous outputs/setpoints; executor catches.
        if self.faults.get("output_on"):
            self.state = replace(self.state, native_r18=1, ha_r18=1)
        if self.faults.get("over_voltage"):
            self.state = replace(self.state, setpoint_v=15.6)
        return self.state


class DisabledLiveGateway:
    def invoke(self, action: Action, evidence: Evidence) -> Evidence:
        raise LiveExecutionDisabled("D094 live hardware actions are disabled")


def verified_off_smoke(e: Evidence) -> None:
    """Require independent, fresh, actual OFF/zero evidence for an OFF-only test."""
    numeric_fields = (
        e.ha_r18, e.native_r18, e.ha_voltage, e.ha_current,
        e.native_voltage, e.native_current, e.ha_age_s,
        e.native_age_s, e.setpoint_v, e.remaining_s,
    )
    # bool is a subclass of int, and NaN/Inf silently defeat comparisons.
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in numeric_fields):
        raise HarnessError("physical evidence requires finite numeric values")
    if not (0 <= e.ha_age_s <= FRESHNESS_S and
            0 <= e.native_age_s <= FRESHNESS_S):
        raise HarnessError("independent HA/native evidence is stale")
    if e.native_measurement_type != "SensorState":
        raise HarnessError("native measurement is not SensorState (NumberState is a setpoint)")
    if any(v != 0 for v in (e.ha_r18, e.native_r18, e.ha_voltage,
                            e.ha_current, e.native_voltage, e.native_current)):
        raise HarnessError("verified Output OFF and measured zero V/I required")
    if not (0 <= e.setpoint_v <= MAX_SETPOINT_V):
        raise HarnessError("setpoint exceeds 15.5 V ceiling or is invalid")
    if type(e.lease_ttl_s) is not int or e.lease_ttl_s != LEASE_TTL_S:
        raise HarnessError("900 s ESPHome passive deadman must remain unchanged")
    if (type(e.owner_count) is not int or e.owner_count != 1 or
            e.handoff_locked is not True):
        raise HarnessError("handoff lock/single-owner invariant failed")
    if (type(e.generation) is not int or e.generation < 0 or
            type(e.armed) is not bool or type(e.autonomous) is not bool or
            type(e.tripped) is not bool or type(e.boot_quarantine) is not bool or
            type(e.authority_conflict) is not bool):
        raise HarnessError("invalid native edge state type or generation")


class D065Executor:
    def __init__(self, gateway: EdgeActionGateway):
        # This release is simulator-only. A future reviewed implementation can
        # deliberately change this gate; no accidental real client can pass it.
        if not isinstance(gateway, OfflineNode):
            raise LiveExecutionDisabled("D094 accepts OfflineNode only; no live channel")
        self.gateway = gateway

    def run(self, action: Action, evidence: Evidence) -> Evidence:
        verified_off_smoke(evidence)
        before = self.gateway.state
        try:
            result = self.gateway.invoke(action, evidence)
            # The callback/result is not proof by itself: require new generation
            # and state assertions matching fresh readback in the offline model.
            expected_generation = before.generation + (0 if action is Action.DISARM else 1)
            if result.generation != expected_generation:
                raise HarnessError("edge generation progression is invalid")
            if result.native_r18 != 0 or result.ha_r18 != 0:
                raise HarnessError("unexpected Output ON")
            if result.setpoint_v > MAX_SETPOINT_V:
                raise HarnessError("setpoint exceeds 15.5 V ceiling")
            if action is Action.RENEW and (not result.armed or result.remaining_s <= 0):
                raise HarnessError("Renew lacks armed and positive remaining confirmation")
            if action is Action.DISARM and (result.armed or result.remaining_s != 0):
                raise HarnessError("Disarm lacks unarmed and zero remaining confirmation")
            if action is Action.ENTER_AUTONOMOUS and (not result.autonomous or result.armed):
                raise HarnessError("Autonomous entry state is not confirmed")
            if action is Action.EXIT_AUTONOMOUS and (result.autonomous or result.armed):
                raise HarnessError("Autonomous exit/managed-idle state is not confirmed")
            return result
        except HarnessError:
            # Simulator-only rollback represents fail-closed containment; it is
            # never an issued command and never evidence of physical behavior.
            self.gateway.state = replace(
                self.gateway.state, ha_r18=0, native_r18=0, ha_voltage=0.0,
                native_voltage=0.0, ha_current=0.0, native_current=0.0,
                armed=False, remaining_s=0.0, autonomous=False, tripped=True,
            )
            raise


class SafeOffPort(Protocol):
    def safe_disable_output_and_verify(self) -> bool: ...


def safe_off_helper(port: SafeOffPort) -> None:
    """Separate fail-closed helper through an explicitly injected existing port."""
    if not port.safe_disable_output_and_verify():
        raise HarnessError("existing verified-OFF port did not prove Output OFF")
