from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional, Protocol


class SafetyViolation(str, Enum):
    TELEMETRY_INVALID = "telemetry_invalid"
    BATTERY_NOT_PLAUSIBLE = "battery_not_plausible"
    BATTERY_TOO_COLD = "battery_too_cold"
    BATTERY_TOO_HOT = "battery_too_hot"
    POWER_SUPPLY_TOO_HOT = "power_supply_too_hot"
    INPUT_VOLTAGE_LOW = "input_voltage_low"
    PROTECTION_ALREADY_TRIPPED = "protection_already_tripped"
    OUTPUT_ALREADY_ON = "output_already_on"
    REQUEST_OVER_RECIPE_CEILING = "request_over_recipe_ceiling"
    REQUEST_OVER_ABSOLUTE_CEILING = "request_over_absolute_ceiling"
    CURRENT_OVER_ABSOLUTE_LIMIT = "current_over_absolute_limit"
    OVP_ENVELOPE_INVALID = "ovp_envelope_invalid"
    OCP_ENVELOPE_INVALID = "ocp_envelope_invalid"
    PROGRAMMING_FAILED = "programming_failed"
    READBACK_MISMATCH = "readback_mismatch"
    OUTPUT_ENABLE_FAILED = "output_enable_failed"
    POST_ENABLE_VERIFY_FAILED = "post_enable_verify_failed"
    OUTPUT_OFF_UNCONFIRMED = "output_off_unconfirmed"


@dataclass(frozen=True)
class SafetyPolicy:
    """Non-negotiable controller envelope, independent from Pb recipe logic."""

    absolute_voltage_ceiling_v: float = 18.0
    absolute_ovp_ceiling_v: float = 18.2
    absolute_current_ceiling_a: float = 12.0
    absolute_ocp_ceiling_a: float = 12.2
    min_battery_voltage_v: float = 2.0
    max_battery_voltage_v: float = 20.0
    min_start_temp_c: float = 10.0
    pause_temp_c: float = 40.0
    critical_temp_c: float = 45.0
    max_internal_temp_c: float = 55.0
    min_input_voltage_v: float = 60.0
    min_ovp_margin_v: float = 0.05
    min_ocp_margin_a: float = 0.05
    voltage_readback_tolerance_v: float = 0.06
    current_readback_tolerance_a: float = 0.06
    protection_readback_tolerance: float = 0.06


@dataclass(frozen=True)
class OutputRequest:
    voltage_v: float
    current_a: float
    ovp_v: float
    ocp_a: float
    recipe_voltage_ceiling_v: float


@dataclass(frozen=True)
class TelemetrySnapshot:
    battery_voltage_v: float
    current_a: float
    temp_ext_c: float
    temp_int_c: float
    input_voltage_v: float
    output_on: bool
    ovp_triggered: bool
    ocp_triggered: bool
    set_voltage_v: Optional[float] = None
    set_current_a: Optional[float] = None
    ovp_v: Optional[float] = None
    ocp_a: Optional[float] = None


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    violations: FrozenSet[SafetyViolation] = field(default_factory=frozenset)
    detail: str = ""


@dataclass(frozen=True)
class EnableResult:
    enabled: bool
    violations: FrozenSet[SafetyViolation] = field(default_factory=frozenset)
    detail: str = ""


class OutputAdapter(Protocol):
    async def get_all_live(self) -> Dict[str, Any]: ...
    async def set_ovp(self, value: float) -> bool: ...
    async def set_ocp(self, value: float) -> bool: ...
    async def set_voltage(self, value: float) -> bool: ...
    async def set_current(self, value: float) -> bool: ...
    async def turn_on(self, entity_id: Optional[str] = None) -> bool: ...
    async def turn_off(self, entity_id: Optional[str] = None) -> bool: ...


def _finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _as_on(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1"}:
            return True
        if normalized in {"off", "false", "0"}:
            return False
    return None


def snapshot_from_live(live: Dict[str, Any]) -> Optional[TelemetrySnapshot]:
    battery_voltage = _finite_float(live.get("battery_voltage"))
    current = _finite_float(live.get("current"))
    temp_ext = _finite_float(live.get("temp_ext"))
    temp_int = _finite_float(live.get("temp_int"))
    input_voltage = _finite_float(live.get("input_voltage"))
    output_on = _as_on(live.get("switch"))
    ovp_triggered = _as_on(live.get("ovp_triggered"))
    ocp_triggered = _as_on(live.get("ocp_triggered"))

    required = (
        battery_voltage,
        current,
        temp_ext,
        temp_int,
        input_voltage,
        output_on,
        ovp_triggered,
        ocp_triggered,
    )
    if any(value is None for value in required):
        return None

    return TelemetrySnapshot(
        battery_voltage_v=battery_voltage,
        current_a=current,
        temp_ext_c=temp_ext,
        temp_int_c=temp_int,
        input_voltage_v=input_voltage,
        output_on=bool(output_on),
        ovp_triggered=bool(ovp_triggered),
        ocp_triggered=bool(ocp_triggered),
        set_voltage_v=_finite_float(live.get("set_voltage")),
        set_current_a=_finite_float(live.get("set_current")),
        ovp_v=_finite_float(live.get("ovp")),
        ocp_a=_finite_float(live.get("ocp")),
    )


class SafetySupervisor:
    def __init__(self, policy: Optional[SafetyPolicy] = None) -> None:
        self.policy = policy or SafetyPolicy()

    def preflight(self, request: OutputRequest, telemetry: TelemetrySnapshot) -> SafetyDecision:
        p = self.policy
        violations: set[SafetyViolation] = set()

        requested = (
            request.voltage_v,
            request.current_a,
            request.ovp_v,
            request.ocp_a,
            request.recipe_voltage_ceiling_v,
        )
        observed = (
            telemetry.battery_voltage_v,
            telemetry.current_a,
            telemetry.temp_ext_c,
            telemetry.temp_int_c,
            telemetry.input_voltage_v,
        )
        if not all(math.isfinite(v) for v in requested + observed):
            violations.add(SafetyViolation.TELEMETRY_INVALID)

        if not (p.min_battery_voltage_v <= telemetry.battery_voltage_v <= p.max_battery_voltage_v):
            violations.add(SafetyViolation.BATTERY_NOT_PLAUSIBLE)
        if telemetry.temp_ext_c < p.min_start_temp_c:
            violations.add(SafetyViolation.BATTERY_TOO_COLD)
        if telemetry.temp_ext_c >= p.pause_temp_c:
            violations.add(SafetyViolation.BATTERY_TOO_HOT)
        if telemetry.temp_int_c >= p.max_internal_temp_c:
            violations.add(SafetyViolation.POWER_SUPPLY_TOO_HOT)
        if telemetry.input_voltage_v < p.min_input_voltage_v:
            violations.add(SafetyViolation.INPUT_VOLTAGE_LOW)
        if telemetry.ovp_triggered or telemetry.ocp_triggered:
            violations.add(SafetyViolation.PROTECTION_ALREADY_TRIPPED)
        if telemetry.output_on:
            violations.add(SafetyViolation.OUTPUT_ALREADY_ON)

        if request.voltage_v > request.recipe_voltage_ceiling_v:
            violations.add(SafetyViolation.REQUEST_OVER_RECIPE_CEILING)
        if (
            request.voltage_v > p.absolute_voltage_ceiling_v
            or request.recipe_voltage_ceiling_v > p.absolute_voltage_ceiling_v
        ):
            violations.add(SafetyViolation.REQUEST_OVER_ABSOLUTE_CEILING)
        if request.current_a <= 0 or request.current_a > p.absolute_current_ceiling_a:
            violations.add(SafetyViolation.CURRENT_OVER_ABSOLUTE_LIMIT)

        if (
            request.ovp_v < request.voltage_v + p.min_ovp_margin_v
            or request.ovp_v > p.absolute_ovp_ceiling_v
        ):
            violations.add(SafetyViolation.OVP_ENVELOPE_INVALID)
        if (
            request.ocp_a < request.current_a + p.min_ocp_margin_a
            or request.ocp_a > p.absolute_ocp_ceiling_a
        ):
            violations.add(SafetyViolation.OCP_ENVELOPE_INVALID)

        return SafetyDecision(
            allowed=not violations,
            violations=frozenset(violations),
            detail=", ".join(sorted(v.value for v in violations)),
        )

    def verify_programmed(self, request: OutputRequest, telemetry: TelemetrySnapshot) -> SafetyDecision:
        p = self.policy
        violations: set[SafetyViolation] = set()
        readbacks = (
            telemetry.set_voltage_v,
            telemetry.set_current_a,
            telemetry.ovp_v,
            telemetry.ocp_a,
        )
        if any(value is None for value in readbacks):
            violations.add(SafetyViolation.READBACK_MISMATCH)
        else:
            assert telemetry.set_voltage_v is not None
            assert telemetry.set_current_a is not None
            assert telemetry.ovp_v is not None
            assert telemetry.ocp_a is not None
            if abs(telemetry.set_voltage_v - request.voltage_v) > p.voltage_readback_tolerance_v:
                violations.add(SafetyViolation.READBACK_MISMATCH)
            if abs(telemetry.set_current_a - request.current_a) > p.current_readback_tolerance_a:
                violations.add(SafetyViolation.READBACK_MISMATCH)
            if abs(telemetry.ovp_v - request.ovp_v) > p.protection_readback_tolerance:
                violations.add(SafetyViolation.READBACK_MISMATCH)
            if abs(telemetry.ocp_a - request.ocp_a) > p.protection_readback_tolerance:
                violations.add(SafetyViolation.READBACK_MISMATCH)

        return SafetyDecision(
            allowed=not violations,
            violations=frozenset(violations),
            detail=", ".join(sorted(v.value for v in violations)),
        )

    def verify_live_output(self, request: OutputRequest, telemetry: TelemetrySnapshot) -> SafetyDecision:
        """Verify the still-live safety envelope after Output ON.

        Unlike ``preflight`` this expects the output to be ON and therefore does not
        classify that state as a violation.  It rechecks PSU/battery/input protection
        and the programmed V/I/OVP/OCP values so an enable cannot succeed merely
        because the pre-ON snapshot was good.
        """
        p = self.policy
        violations: set[SafetyViolation] = set()
        if not telemetry.output_on:
            violations.add(SafetyViolation.POST_ENABLE_VERIFY_FAILED)
        if not (p.min_battery_voltage_v <= telemetry.battery_voltage_v <= p.max_battery_voltage_v):
            violations.add(SafetyViolation.BATTERY_NOT_PLAUSIBLE)
        if telemetry.temp_ext_c >= p.pause_temp_c:
            violations.add(SafetyViolation.BATTERY_TOO_HOT)
        if telemetry.temp_int_c >= p.max_internal_temp_c:
            violations.add(SafetyViolation.POWER_SUPPLY_TOO_HOT)
        if telemetry.input_voltage_v < p.min_input_voltage_v:
            violations.add(SafetyViolation.INPUT_VOLTAGE_LOW)
        if telemetry.ovp_triggered or telemetry.ocp_triggered:
            violations.add(SafetyViolation.PROTECTION_ALREADY_TRIPPED)
        if telemetry.current_a > p.absolute_ocp_ceiling_a + p.current_readback_tolerance_a:
            violations.add(SafetyViolation.CURRENT_OVER_ABSOLUTE_LIMIT)

        programmed = self.verify_programmed(request, telemetry)
        violations.update(programmed.violations)
        return SafetyDecision(
            allowed=not violations,
            violations=frozenset(violations),
            detail=", ".join(sorted(v.value for v in violations)),
        )


class SafeOutputCoordinator:
    """Fail-closed output enable sequence.

    Protections are programmed first, then setpoints, then all four values are
    read back. Output is enabled only after those checks pass. Any failure tries
    to force the output OFF; if OFF itself cannot be confirmed, that fact is
    propagated explicitly instead of reporting a falsely safe state.
    """

    def __init__(
        self,
        adapter: OutputAdapter,
        supervisor: Optional[SafetySupervisor] = None,
        *,
        readback_delay_s: float = 0.0,
    ) -> None:
        self.adapter = adapter
        self.supervisor = supervisor or SafetySupervisor()
        self.readback_delay_s = max(0.0, readback_delay_s)

    async def _force_off(self) -> bool:
        try:
            return bool(await self.adapter.turn_off())
        except Exception:
            return False

    async def _failure(
        self,
        violations: FrozenSet[SafetyViolation],
        detail: str,
        *,
        force_off: bool,
    ) -> EnableResult:
        merged = set(violations)
        if force_off and not await self._force_off():
            merged.add(SafetyViolation.OUTPUT_OFF_UNCONFIRMED)
            detail = f"{detail}; output OFF was not confirmed"
        return EnableResult(False, frozenset(merged), detail)

    async def enable(self, request: OutputRequest) -> EnableResult:
        live = await self.adapter.get_all_live()
        before = snapshot_from_live(live)
        if before is None:
            return EnableResult(
                False,
                frozenset({SafetyViolation.TELEMETRY_INVALID}),
                "required live telemetry is missing or invalid",
            )

        decision = self.supervisor.preflight(request, before)
        if not decision.allowed:
            return EnableResult(False, decision.violations, decision.detail)

        operations = (
            (self.adapter.set_ovp, request.ovp_v),
            (self.adapter.set_ocp, request.ocp_a),
            (self.adapter.set_voltage, request.voltage_v),
            (self.adapter.set_current, request.current_a),
        )
        for setter, value in operations:
            try:
                ok = await setter(value)
            except Exception:
                ok = False
            if not ok:
                return await self._failure(
                    frozenset({SafetyViolation.PROGRAMMING_FAILED}),
                    f"failed to program {value}",
                    force_off=True,
                )

        if self.readback_delay_s:
            await asyncio.sleep(self.readback_delay_s)

        programmed_live = await self.adapter.get_all_live()
        programmed = snapshot_from_live(programmed_live)
        if programmed is None:
            return await self._failure(
                frozenset({SafetyViolation.READBACK_MISMATCH}),
                "programmed values could not be read back",
                force_off=True,
            )

        second_preflight = self.supervisor.preflight(request, programmed)
        if not second_preflight.allowed:
            return await self._failure(
                second_preflight.violations,
                second_preflight.detail,
                force_off=True,
            )

        verified = self.supervisor.verify_programmed(request, programmed)
        if not verified.allowed:
            return await self._failure(
                verified.violations,
                verified.detail,
                force_off=True,
            )

        try:
            enabled = await self.adapter.turn_on()
        except Exception:
            enabled = False
        if not enabled:
            return await self._failure(
                frozenset({SafetyViolation.OUTPUT_ENABLE_FAILED}),
                "output enable command failed",
                force_off=True,
            )

        if self.readback_delay_s:
            await asyncio.sleep(self.readback_delay_s)
        final_live = await self.adapter.get_all_live()
        final = snapshot_from_live(final_live)
        if final is None:
            return await self._failure(
                frozenset({SafetyViolation.POST_ENABLE_VERIFY_FAILED}),
                "post-enable required telemetry is missing/invalid",
                force_off=True,
            )

        final_decision = self.supervisor.verify_live_output(request, final)
        if not final_decision.allowed:
            return await self._failure(
                final_decision.violations | frozenset({SafetyViolation.POST_ENABLE_VERIFY_FAILED}),
                final_decision.detail or "post-enable state is not safe/confirmed",
                force_off=True,
            )

        return EnableResult(True)
