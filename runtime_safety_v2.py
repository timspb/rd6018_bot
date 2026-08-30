from __future__ import annotations

import math
import time
from typing import Any, Optional

from charge_logic import MAX_STAGE_CURRENT
from rd6018_telemetry import ProtectionStatus, resolve_protection, telemetry_freshness
from runtime_safety import RuntimeSafetyError, _binary, _finite
from runtime_safety_strict import StrictRuntimeSafetyGuard


class V2RuntimeSafetyGuard(StrictRuntimeSafetyGuard):
    """Production guard aligned with the accepted V2 authority model.

    Vin is PSU-health telemetry, not chemistry/FSM authority.  The legacy/base guard
    keeps its historic fail-closed Vin rule for rollback compatibility; production V2
    deliberately removes only that authority while retaining all hard battery,
    protection, readback, watchdog and edge-lease checks.

    The class also reserves a first-class authority hook for an explicit ManualSession:
    a manual session is managed output, not an orphan output, and uses the absolute
    17.5 V envelope rather than the legacy 16.6 V profile ceiling.
    """

    # These are continuously sampled physical channels. Their source timestamps are
    # suitable for stale-data detection. Static configuration/readback entities such as
    # OVP/OCP/Vset/Iset are still validated every poll, but their HA timestamps are not
    # used as heartbeats because an unchanged setpoint may legitimately remain unchanged
    # for hours. The local edge lease independently proves fresh RD6018 Modbus + Output
    # register access in production.
    RUNTIME_FRESHNESS_KEYS = (
        "battery_voltage",
        "current",
        "temp_ext",
        "temp_int",
    )

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self._install_last_reported_metadata_bridge()

    def _install_last_reported_metadata_bridge(self) -> None:
        """Preserve HA's heartbeat timestamp without changing the legacy adapter.

        Home Assistant exposes ``last_reported`` even when an entity's value did not
        change. Legacy HassClient predates that field and only copies ``last_updated``.
        Patch its metadata formatter at the V2 boundary so flat battery temperature or
        current does not look stale merely because the numeric value stayed identical.
        """
        if getattr(self.hass, "_v2_last_reported_metadata_bridge", False):
            return
        formatter = getattr(self.hass, "_entity_metadata", None)
        if not callable(formatter):
            return

        def _with_last_reported(entity_id: str, data: dict[str, Any], status: str) -> dict[str, Any]:
            metadata = dict(formatter(entity_id, data, status))
            metadata["last_reported"] = data.get("last_reported")
            return metadata

        self.hass._entity_metadata = _with_last_reported
        self.hass._v2_last_reported_metadata_bridge = True

    @property
    def manual_active(self) -> bool:
        manager = getattr(self.app, "manual_session_manager", None)
        return bool(manager is not None and getattr(manager, "is_active", False))

    @property
    def controller_active(self) -> bool:
        return super().controller_active or self.manual_active

    def _recipe_voltage_ceiling(self) -> float:
        if self.manual_active:
            return float(self.policy.absolute_voltage_ceiling_v)
        return super()._recipe_voltage_ceiling()

    def _critical_telemetry_error(
        self,
        live: dict[str, Any],
        *,
        require_programming: bool,
    ) -> Optional[str]:
        # Vin is intentionally absent. Missing/low Vin may be surfaced by PSU-health
        # diagnostics but may not masquerade as a battery safety event.
        numeric_keys = ["battery_voltage", "current", "temp_ext", "temp_int"]
        if require_programming:
            # V_OUT is measured physical output, distinct from configured Vset. Once
            # Output is ON it is part of the hard actuator envelope and may not vanish.
            numeric_keys.append("voltage")
        for key in numeric_keys:
            if _finite(live.get(key)) is None:
                return f"required telemetry {key} is missing/unavailable"

        if _binary(live.get("switch")) is None:
            return "required telemetry switch is missing/unavailable"

        raw_protection_available = live.get("protection_code") not in (
            None,
            "",
            "unknown",
            "unavailable",
        )
        if not raw_protection_available:
            for key in ("ovp_triggered", "ocp_triggered"):
                if _binary(live.get(key)) is None:
                    return f"required telemetry {key} is missing/unavailable"

        protection = resolve_protection(live)
        if protection.status is ProtectionStatus.UNKNOWN:
            return "RD6018 protection status is unknown"
        # Legacy runtime knows how to report OVP/OCP precisely. OPP has no legacy
        # boolean trip path, so V2 must fail closed here instead of silently missing it.
        if protection.status is ProtectionStatus.OPP:
            return "RD6018 OPP protection is tripped"

        battery_v = _finite(live.get("battery_voltage"))
        assert battery_v is not None
        if not (
            self.policy.min_battery_voltage_v
            <= battery_v
            <= self.policy.max_battery_voltage_v
        ):
            return f"battery voltage is implausible: {battery_v:.3f}V"

        temp_ext = _finite(live.get("temp_ext"))
        temp_int = _finite(live.get("temp_int"))
        assert temp_ext is not None and temp_int is not None
        if temp_ext >= self.policy.critical_temp_c:
            return f"battery temperature {temp_ext:.1f}C is critical"
        if temp_int >= self.policy.max_internal_temp_c:
            return f"power-supply temperature {temp_int:.1f}C is critical"

        if require_programming:
            for key in ("set_voltage", "set_current", "ovp", "ocp"):
                if _finite(live.get(key)) is None:
                    return f"live protection/readback {key} is missing/unavailable"
        return None

    def _runtime_freshness_error(
        self,
        live: dict[str, Any],
        *,
        output_state: Optional[bool],
    ) -> Optional[str]:
        keys = list(self.RUNTIME_FRESHNESS_KEYS)
        if output_state is True:
            keys.append("voltage")
        freshness = telemetry_freshness(live, keys)
        if freshness.valid:
            return None
        return f"critical runtime telemetry is stale/incoherent: {freshness.detail}"

    def _runtime_envelope_error(self, live: dict[str, Any]) -> Optional[str]:
        protection = resolve_protection(live)
        # A real OVP/OCP trip is handled by the strict hardware-trip path below so the
        # existing operator event can still identify the exact trip. Unknown/OPP were
        # already rejected by _critical_telemetry_error().
        if protection.status in {ProtectionStatus.OVP, ProtectionStatus.OCP}:
            return None

        set_v = _finite(live.get("set_voltage"))
        set_i = _finite(live.get("set_current"))
        ovp = _finite(live.get("ovp"))
        ocp = _finite(live.get("ocp"))
        actual_v = _finite(live.get("voltage"))
        actual_i = _finite(live.get("current"))
        if None in (set_v, set_i, ovp, ocp, actual_v, actual_i):
            return "programming/readback/measured output became invalid while output was ON"
        assert (
            set_v is not None
            and set_i is not None
            and ovp is not None
            and ocp is not None
            and actual_v is not None
            and actual_i is not None
        )

        recipe_ceiling = self._recipe_voltage_ceiling()
        if set_v > recipe_ceiling + self.READBACK_TOLERANCE:
            return f"set voltage {set_v:.3f}V exceeds recipe ceiling {recipe_ceiling:.3f}V"
        if set_v > self.policy.absolute_voltage_ceiling_v + self.READBACK_TOLERANCE:
            return f"set voltage {set_v:.3f}V exceeds absolute ceiling"
        if actual_v > recipe_ceiling + self.READBACK_TOLERANCE:
            return f"measured output voltage {actual_v:.3f}V exceeds recipe ceiling {recipe_ceiling:.3f}V"
        if actual_v > self.policy.absolute_voltage_ceiling_v + self.READBACK_TOLERANCE:
            return f"measured output voltage {actual_v:.3f}V exceeds absolute ceiling"
        if actual_v > ovp + self.READBACK_TOLERANCE:
            return f"measured output voltage {actual_v:.3f}V exceeds configured OVP {ovp:.3f}V"
        if set_i <= 0 or set_i > float(MAX_STAGE_CURRENT) + self.READBACK_TOLERANCE:
            return f"set current {set_i:.3f}A exceeds runtime envelope"
        if actual_i > self.policy.absolute_current_ceiling_a + self.READBACK_TOLERANCE:
            return f"measured current {actual_i:.3f}A exceeds absolute working-current envelope"
        if actual_i > ocp + self.READBACK_TOLERANCE:
            return f"measured current {actual_i:.3f}A exceeds configured OCP {ocp:.3f}A"
        if ovp > self.policy.absolute_ovp_ceiling_v + self.READBACK_TOLERANCE:
            return f"OVP {ovp:.3f}V exceeds absolute protection ceiling"
        if ocp > self.policy.absolute_ocp_ceiling_a + self.READBACK_TOLERANCE:
            return f"OCP {ocp:.3f}A exceeds absolute protection ceiling"
        if ovp + self.READBACK_TOLERANCE < set_v + self.PROTECTION_MARGIN:
            return f"OVP {ovp:.3f}V does not protect set voltage {set_v:.3f}V"
        if ocp + self.READBACK_TOLERANCE < set_i + self.PROTECTION_MARGIN:
            return f"OCP {ocp:.3f}A does not protect set current {set_i:.3f}A"
        return None

    def _stage_target(self, live: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
        if self.manual_active:
            manager = getattr(self.app, "manual_session_manager", None)
            request = getattr(manager, "request", None)
            if request is not None:
                return _finite(getattr(request, "voltage_v", None)), _finite(
                    getattr(request, "current_a", None)
                )
        return super()._stage_target(live)

    async def get_all_live(self) -> dict[str, Any]:
        """Strict production checks without granting Vin actuator authority."""
        live = await self._raw_live()
        output_state = _binary(live.get("switch"))
        safety_relevant = self.controller_active or output_state is True or self._off_unconfirmed
        if not safety_relevant:
            self._orphan_output_seen_at = None
            return live

        error = self._critical_telemetry_error(
            live,
            require_programming=output_state is True,
        )
        if error is not None:
            await self._fail_closed("telemetry_invalid", error, output_state=output_state)

        freshness_error = self._runtime_freshness_error(
            live,
            output_state=output_state,
        )
        if freshness_error is not None:
            await self._fail_closed(
                "telemetry_stale",
                freshness_error,
                output_state=output_state,
            )

        if output_state is False:
            self._off_unconfirmed = False
            self._orphan_output_seen_at = None
            return live

        if output_state is True and not self.controller_active:
            now = time.monotonic()
            if self._orphan_output_seen_at is None:
                self._orphan_output_seen_at = now
                return live
            if now - self._orphan_output_seen_at >= self.ORPHAN_OUTPUT_GRACE_S:
                await self._fail_closed(
                    "unmanaged_output",
                    "RD6018 output remains ON without a managed/restored session",
                    output_state=True,
                )
            return live

        if output_state is True:
            envelope_error = self._runtime_envelope_error(live)
            if envelope_error is not None:
                await self._fail_closed(
                    "runtime_envelope",
                    envelope_error,
                    output_state=True,
                )

            protection = resolve_protection(live)
            if protection.status in {ProtectionStatus.OVP, ProtectionStatus.OCP}:
                await self._ensure_output_off(
                    f"hardware {protection.status.value.upper()} protection trip"
                )
                return live

            temp_int = _finite(live.get("temp_int"))
            if (
                temp_int is not None
                and temp_int >= float(self.policy.max_internal_temp_c)
            ):
                await self._fail_closed(
                    "psu_temperature_high",
                    f"RD6018 temperature {temp_int:.1f}C >= {self.policy.max_internal_temp_c:.1f}C",
                    output_state=True,
                )

            await self._renew_edge_lease_or_fail(output_state=True)

        return live


def install_v2_runtime_safety(app: Any) -> V2RuntimeSafetyGuard:
    existing = getattr(app.hass, "_runtime_safety_guard", None)
    if isinstance(existing, V2RuntimeSafetyGuard):
        return existing
    if existing is not None:
        raise RuntimeError("runtime safety guard was installed before V2 production guard")
    guard = V2RuntimeSafetyGuard(app)
    guard.install()
    app.runtime_safety_guard = guard
    return guard
