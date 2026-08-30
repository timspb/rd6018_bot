from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional, Protocol

from rd6018_telemetry import (
    ProtectionStatus,
    RegulationMode,
    as_bool,
    finite_float,
    resolve_protection,
    resolve_regulation,
    telemetry_freshness,
)

logger = logging.getLogger("rd6018")


class SafetyViolation(str, Enum):
    TELEMETRY_INVALID = "telemetry_invalid"
    BATTERY_NOT_PLAUSIBLE = "battery_not_plausible"
    BATTERY_TOO_COLD = "battery_too_cold"
    BATTERY_TOO_HOT = "battery_too_hot"
    POWER_SUPPLY_TOO_HOT = "power_supply_too_hot"
    # Kept as a compatibility enum for old logs/API consumers. Vin is PSU-health
    # telemetry in V2 and no longer grants/denies charge authority.
    INPUT_VOLTAGE_LOW = "input_voltage_low"
    PROTECTION_ALREADY_TRIPPED = "protection_already_tripped"
    UNKNOWN_HARDWARE_PROTECTION = "unknown_hardware_protection"
    UNSAFE_HARDWARE_CONFIGURATION = "unsafe_hardware_configuration"
    OUTPUT_ALREADY_ON = "output_already_on"
    REQUEST_OVER_RECIPE_CEILING = "request_over_recipe_ceiling"
    REQUEST_OVER_ABSOLUTE_CEILING = "request_over_absolute_ceiling"
    MEASURED_OUTPUT_OVER_LIMIT = "measured_output_over_limit"
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

    # User-facing/manual setpoint ceiling. 17.5 V is accepted; anything above it
    # is rejected before the RD6018 output is armed.
    absolute_voltage_ceiling_v: float = 17.5
    # OVP is calculated from the target, so it needs one protection margin above
    # the maximum accepted 17.5 V working setpoint.
    absolute_ovp_ceiling_v: float = 17.6
    absolute_current_ceiling_a: float = 12.0
    absolute_ocp_ceiling_a: float = 12.2
    min_battery_voltage_v: float = 2.0
    max_battery_voltage_v: float = 20.0
    min_start_temp_c: float = 10.0
    pause_temp_c: float = 40.0
    critical_temp_c: float = 45.0
    max_internal_temp_c: float = 55.0
    # Retained as a PSU-health reference only; it is deliberately not a safety gate.
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
    output_on: bool
    ovp_triggered: bool
    ocp_triggered: bool
    input_voltage_v: Optional[float] = None
    output_voltage_v: Optional[float] = None
    protection_status: ProtectionStatus = ProtectionStatus.NORMAL
    protection_unknown: bool = False
    regulation_mode: RegulationMode = RegulationMode.UNKNOWN
    battery_mode: Optional[bool] = None
    boot_power: Optional[bool] = None
    take_out: Optional[bool] = None
    take_ok: Optional[bool] = None
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


def _protection_freshness_keys(live: Dict[str, Any]) -> list[str]:
    if live.get("protection_code") not in (None, "", "unknown", "unavailable"):
        return ["protection_code"]
    return ["ovp_triggered", "ocp_triggered"]


def snapshot_from_live(
    live: Dict[str, Any],
    *,
    require_programming_freshness: bool = False,
) -> Optional[TelemetrySnapshot]:
    """Build a safety snapshot with context-appropriate freshness semantics.

    Dynamic physical/status channels are always freshness-gated. Static V/I/OVP/OCP
    readback values are freshness-gated only after a programming transaction, when the
    caller is explicitly proving that the just-written configuration reached HA/RD.
    This prevents hours-old unchanged setpoint timestamps from blocking a new preflight
    while preserving fresh-readback proof before/after Output ON.
    """
    battery_voltage = finite_float(live.get("battery_voltage"))
    output_voltage = finite_float(live.get("voltage"))
    current = finite_float(live.get("current"))
    temp_ext = finite_float(live.get("temp_ext"))
    temp_int = finite_float(live.get("temp_int"))
    input_voltage = finite_float(live.get("input_voltage"))
    output_on = as_bool(live.get("switch"))
    protection = resolve_protection(live)

    # BAT_MODE is deliberately not a permission to start charging. It is RD6018
    # physical-state feedback: the hardware itself decides whether it can close the
    # battery relay. Keep it observational in this snapshot.
    battery_mode = as_bool(live.get("battery_mode"))
    boot_power = as_bool(live.get("boot_power"))
    take_out = as_bool(live.get("take_out"))
    take_ok = as_bool(live.get("take_ok"))

    required = (battery_voltage, current, temp_ext, temp_int, output_on)
    if any(value is None for value in required):
        return None

    freshness_keys = ["battery_voltage", "current", "temp_ext", "temp_int", "switch"]
    if output_voltage is not None:
        freshness_keys.append("voltage")
    freshness_keys.extend(_protection_freshness_keys(live))
    if require_programming_freshness:
        for key in ("set_voltage", "set_current", "ovp", "ocp"):
            if live.get(key) not in (None, "", "unknown", "unavailable"):
                freshness_keys.append(key)
    freshness = telemetry_freshness(live, freshness_keys)
    if not freshness.valid:
        logger.warning("Rejecting stale/incoherent HA telemetry: %s", freshness.detail)
        return None

    return TelemetrySnapshot(
        battery_voltage_v=float(battery_voltage),
        output_voltage_v=output_voltage,
        current_a=float(current),
        temp_ext_c=float(temp_ext),
        temp_int_c=float(temp_int),
        input_voltage_v=input_voltage,
        output_on=bool(output_on),
        ovp_triggered=protection.ovp,
        ocp_triggered=protection.ocp,
        protection_status=protection.status,
        protection_unknown=protection.unknown,
        regulation_mode=resolve_regulation(live),
        battery_mode=battery_mode,
        boot_power=boot_power,
        take_out=take_out,
        take_ok=take_ok,
        set_voltage_v=finite_float(live.get("set_voltage")),
        set_current_a=finite_float(live.get("set_current")),
        ovp_v=finite_float(live.get("ovp")),
        ocp_a=finite_float(live.get("ocp")),
    )


class SafetySupervisor:
    def __init__(self, policy: Optional[SafetyPolicy] = None) -> None:
        self.policy = policy or SafetyPolicy()

    @staticmethod
    def _hardware_config_violations(telemetry: TelemetrySnapshot) -> set[SafetyViolation]:
        violations: set[SafetyViolation] = set()
        # These registers are optional during migration. If exposed, an automatically
        # enabling RD6018 configuration is incompatible with managed charging.
        if telemetry.boot_power is True or telemetry.take_out is True:
            violations.add(SafetyViolation.UNSAFE_HARDWARE_CONFIGURATION)
        return violations

    @staticmethod
    def _protection_violations(telemetry: TelemetrySnapshot) -> set[SafetyViolation]:
        violations: set[SafetyViolation] = set()
        if telemetry.protection_unknown:
            violations.add(SafetyViolation.UNKNOWN_HARDWARE_PROTECTION)
        elif telemetry.protection_status is not ProtectionStatus.NORMAL:
            violations.add(SafetyViolation.PROTECTION_ALREADY_TRIPPED)
        return violations

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
        # Vin is intentionally diagnostic-only. A weak/failed upstream PSU may be
        # reported by health diagnostics but cannot redefine the battery chemistry FSM.
        violations.update(self._protection_violations(telemetry))
        violations.update(self._hardware_config_violations(telemetry))
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
        mismatches: list[str] = []
        checks = (
            ("set_voltage", telemetry.set_voltage_v, request.voltage_v, p.voltage_readback_tolerance_v),
            ("set_current", telemetry.set_current_a, request.current_a, p.current_readback_tolerance_a),
            ("ovp", telemetry.ovp_v, request.ovp_v, p.protection_readback_tolerance),
            ("ocp", telemetry.ocp_a, request.ocp_a, p.protection_readback_tolerance),
        )
        for name, actual, expected, tolerance in checks:
            if actual is None:
                mismatches.append(f"{name}=missing expected={expected:.3f}")
            elif abs(actual - expected) > tolerance:
                mismatches.append(
                    f"{name} actual={actual:.3f} expected={expected:.3f} tol={tolerance:.3f}"
                )

        violations = frozenset({SafetyViolation.READBACK_MISMATCH}) if mismatches else frozenset()
        return SafetyDecision(
            allowed=not mismatches,
            violations=violations,
            detail="; ".join(mismatches),
        )

    def verify_live_output(self, request: OutputRequest, telemetry: TelemetrySnapshot) -> SafetyDecision:
        """Verify measured + configured hard safety after Output ON."""
        p = self.policy
        violations: set[SafetyViolation] = set()
        details: list[str] = []
        if not telemetry.output_on:
            violations.add(SafetyViolation.POST_ENABLE_VERIFY_FAILED)
        if not (p.min_battery_voltage_v <= telemetry.battery_voltage_v <= p.max_battery_voltage_v):
            violations.add(SafetyViolation.BATTERY_NOT_PLAUSIBLE)
        if telemetry.temp_ext_c >= p.pause_temp_c:
            violations.add(SafetyViolation.BATTERY_TOO_HOT)
        if telemetry.temp_int_c >= p.max_internal_temp_c:
            violations.add(SafetyViolation.POWER_SUPPLY_TOO_HOT)
        violations.update(self._protection_violations(telemetry))
        violations.update(self._hardware_config_violations(telemetry))

        if telemetry.output_voltage_v is None:
            violations.add(SafetyViolation.TELEMETRY_INVALID)
            details.append("measured output voltage is missing")
        else:
            measured_v_limit = min(
                p.absolute_voltage_ceiling_v,
                request.recipe_voltage_ceiling_v,
            )
            if telemetry.output_voltage_v > measured_v_limit + p.voltage_readback_tolerance_v:
                violations.add(SafetyViolation.MEASURED_OUTPUT_OVER_LIMIT)
                details.append(
                    f"measured output voltage {telemetry.output_voltage_v:.3f} exceeds "
                    f"working ceiling {measured_v_limit:.3f}"
                )
            if telemetry.output_voltage_v > request.ovp_v + p.protection_readback_tolerance:
                violations.add(SafetyViolation.MEASURED_OUTPUT_OVER_LIMIT)
                details.append(
                    f"measured output voltage {telemetry.output_voltage_v:.3f} exceeds "
                    f"configured OVP {request.ovp_v:.3f}"
                )

        if telemetry.current_a > p.absolute_current_ceiling_a + p.current_readback_tolerance_a:
            violations.add(SafetyViolation.CURRENT_OVER_ABSOLUTE_LIMIT)
            details.append(
                f"measured current {telemetry.current_a:.3f} exceeds working ceiling "
                f"{p.absolute_current_ceiling_a:.3f}"
            )
        if telemetry.current_a > request.ocp_a + p.protection_readback_tolerance:
            violations.add(SafetyViolation.CURRENT_OVER_ABSOLUTE_LIMIT)
            details.append(
                f"measured current {telemetry.current_a:.3f} exceeds configured OCP "
                f"{request.ocp_a:.3f}"
            )

        programmed = self.verify_programmed(request, telemetry)
        violations.update(programmed.violations)
        if programmed.detail:
            details.append(programmed.detail)
        if not details and violations:
            details.append(", ".join(sorted(v.value for v in violations)))
        return SafetyDecision(
            allowed=not violations,
            violations=frozenset(violations),
            detail="; ".join(details),
        )


class SafeOutputCoordinator:
    """Fail-closed output enable sequence with setpoint readback."""

    def __init__(
        self,
        adapter: OutputAdapter,
        supervisor: Optional[SafetySupervisor] = None,
        *,
        readback_delay_s: float = 0.0,
        readback_timeout_s: float = 6.0,
        readback_poll_interval_s: float = 0.25,
    ) -> None:
        self.adapter = adapter
        self.supervisor = supervisor or SafetySupervisor()
        self.readback_delay_s = max(0.0, readback_delay_s)
        self.readback_timeout_s = max(0.0, readback_timeout_s)
        self.readback_poll_interval_s = max(0.01, readback_poll_interval_s)

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
        logger.warning(
            "Safe output enable failed: %s [%s]",
            detail,
            ",".join(sorted(v.value for v in merged)),
        )
        return EnableResult(False, frozenset(merged), detail)

    async def _wait_for_programmed_readback(
        self,
        request: OutputRequest,
    ) -> tuple[Optional[TelemetrySnapshot], SafetyDecision]:
        if self.readback_delay_s:
            await asyncio.sleep(self.readback_delay_s)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.readback_timeout_s
        last_mismatch = SafetyDecision(
            False,
            frozenset({SafetyViolation.READBACK_MISMATCH}),
            "programmed values were not observed",
        )
        last_exception: Optional[Exception] = None

        while True:
            programmed: Optional[TelemetrySnapshot] = None
            try:
                programmed_live = await self.adapter.get_all_live()
                programmed = snapshot_from_live(
                    programmed_live,
                    require_programming_freshness=True,
                )
                last_exception = None
            except Exception as exc:
                last_exception = exc

            if programmed is not None:
                second_preflight = self.supervisor.preflight(request, programmed)
                if not second_preflight.allowed:
                    return programmed, second_preflight

                verified = self.supervisor.verify_programmed(request, programmed)
                if verified.allowed:
                    return programmed, verified
                last_mismatch = verified

            now = loop.time()
            if now >= deadline:
                if programmed is None:
                    detail = "programmed readback telemetry missing/invalid"
                    if last_exception is not None:
                        detail += f": {type(last_exception).__name__}: {last_exception}"
                    return None, SafetyDecision(
                        False,
                        frozenset({SafetyViolation.TELEMETRY_INVALID}),
                        detail,
                    )
                return programmed, last_mismatch

            await asyncio.sleep(min(self.readback_poll_interval_s, max(0.0, deadline - now)))

    async def enable(self, request: OutputRequest) -> EnableResult:
        try:
            live = await self.adapter.get_all_live()
        except Exception as exc:
            return EnableResult(
                False,
                frozenset({SafetyViolation.TELEMETRY_INVALID}),
                f"pre-enable telemetry failed: {type(exc).__name__}: {exc}",
            )
        before = snapshot_from_live(live, require_programming_freshness=False)
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
            ("ovp", self.adapter.set_ovp, request.ovp_v),
            ("ocp", self.adapter.set_ocp, request.ocp_a),
            ("voltage", self.adapter.set_voltage, request.voltage_v),
            ("current", self.adapter.set_current, request.current_a),
        )
        for name, setter, value in operations:
            try:
                ok = await setter(value)
            except Exception as exc:
                return await self._failure(
                    frozenset({SafetyViolation.PROGRAMMING_FAILED}),
                    f"failed to program {name}={value:.3f}: {type(exc).__name__}: {exc}",
                    force_off=True,
                )
            if not ok:
                return await self._failure(
                    frozenset({SafetyViolation.PROGRAMMING_FAILED}),
                    f"failed to program {name}={value:.3f}",
                    force_off=True,
                )

        _programmed, readback = await self._wait_for_programmed_readback(request)
        if not readback.allowed:
            return await self._failure(readback.violations, readback.detail, force_off=True)

        try:
            enabled = await self.adapter.turn_on()
        except Exception as exc:
            return await self._failure(
                frozenset({SafetyViolation.OUTPUT_ENABLE_FAILED}),
                f"output enable raised {type(exc).__name__}: {exc}",
                force_off=True,
            )
        if not enabled:
            return await self._failure(
                frozenset({SafetyViolation.OUTPUT_ENABLE_FAILED}),
                "output enable command returned false",
                force_off=True,
            )

        if self.readback_delay_s:
            await asyncio.sleep(self.readback_delay_s)
        try:
            final_live = await self.adapter.get_all_live()
        except Exception as exc:
            return await self._failure(
                frozenset(
                    {
                        SafetyViolation.TELEMETRY_INVALID,
                        SafetyViolation.POST_ENABLE_VERIFY_FAILED,
                    }
                ),
                f"post-enable telemetry failed: {type(exc).__name__}: {exc}",
                force_off=True,
            )
        final = snapshot_from_live(
            final_live,
            require_programming_freshness=True,
        )
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
