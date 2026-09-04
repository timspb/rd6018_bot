"""Typed HANDS_OFF -> PB_MANAGED physical-test transition on the existing AF_UNIX plane.

The operation is intentionally narrower than the Telegram operator action: it is
available only while the opt-in physical-test server is enabled, accepts no parameters,
requires canonical Output OFF plus a clean edge/runtime state, and delegates the actual
durable ownership transition to the already-installed RdControlModeManager.  It never
writes RD6018/HA actuator values and never creates another listener.
"""
from __future__ import annotations

from typing import Any, Dict

from physical_test_control import PhysicalTestControl, PhysicalTestControlError, _json_value
from rd6018_telemetry import finite_float


_OPERATION = "return_pb_control_verified_off"
_MAX_MODBUS_AGE_S = 20.0
_PROGRAMMED_KEYS = ("set_voltage", "set_current", "ovp", "ocp")


class PhysicalTestControlPbMode:
    """One strictly typed, non-actuating PB ownership-return operation."""

    def __init__(self, app: Any, control: PhysicalTestControl) -> None:
        self.app = app
        self.control = control
        self._original_dispatch = control.dispatch

    @staticmethod
    def _inactive(obj: Any) -> bool:
        return not bool(getattr(obj, "active", False)) and not bool(
            getattr(obj, "is_active", False)
        ) and not bool(getattr(obj, "off_pending", False))

    @staticmethod
    def _programmed_values(live: Dict[str, Any]) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for key in _PROGRAMMED_KEYS:
            value = finite_float(live.get(key))
            if value is None:
                raise PhysicalTestControlError(
                    f"PB control return requires numeric {key} readback"
                )
            values[key] = float(value)
        return values

    @staticmethod
    def _same_programmed_values(before: Dict[str, float], after: Dict[str, Any]) -> bool:
        for key, expected in before.items():
            observed = finite_float(after.get(key))
            if observed is None or abs(float(observed) - expected) > 1e-6:
                return False
        return True

    async def return_pb_control_verified_off(self) -> Dict[str, Any]:
        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is None or not bool(getattr(manager, "hands_off", False)):
            raise PhysicalTestControlError(
                "PB control return requires durable/in-memory HANDS_OFF"
            )
        if bool(getattr(manager, "release_in_progress", False)):
            raise PhysicalTestControlError(
                "PB control return rejected during ownership transfer"
            )

        for name in (
            "charge_controller",
            "manual_session_manager",
            "rd_managed_live_adoption",
            "rd_managed_mix_adoption",
        ):
            if not self._inactive(getattr(self.app, name, None)):
                raise PhysicalTestControlError(
                    f"PB control return requires no active managed authority ({name})"
                )

        guard = getattr(self.app, "runtime_safety_guard", None)
        if guard is None:
            raise PhysicalTestControlError("PB control return safety guard unavailable")
        if bool(getattr(guard, "_off_unconfirmed", False)):
            raise PhysicalTestControlError(
                "PB control return blocked while Output OFF remains unconfirmed"
            )

        live_before = await self.control._raw_live()
        if not self.control._is_off(live_before):
            raise PhysicalTestControlError(
                "PB control return requires canonical Output OFF / register-18 V2=0"
            )
        try:
            protection = int(float(live_before.get("protection_code")))
        except (TypeError, ValueError) as exc:
            raise PhysicalTestControlError(
                "PB control return requires authoritative Protection=0"
            ) from exc
        if protection != 0:
            raise PhysicalTestControlError(
                "PB control return requires authoritative Protection=0"
            )

        programmed_before = self._programmed_values(live_before)
        lease_before = await self.control._lease_state()
        try:
            modbus_age_s = float(lease_before.modbus_age_s)
            remaining_s = float(lease_before.remaining_s)
        except (TypeError, ValueError, AttributeError) as exc:
            raise PhysicalTestControlError(
                "PB control return requires readable edge lease state"
            ) from exc
        if (
            bool(lease_before.armed)
            or bool(lease_before.tripped)
            or bool(lease_before.boot_quarantine)
            or remaining_s > 0.0
            or modbus_age_s > _MAX_MODBUS_AGE_S
        ):
            raise PhysicalTestControlError(
                "PB control return requires clean/unarmed edge state and fresh Modbus"
            )

        transition = getattr(manager, "return_pb_control", None)
        if not callable(transition):
            raise PhysicalTestControlError("PB control return manager API unavailable")
        returned = bool(await transition())
        if not returned or not bool(getattr(manager, "pb_managed", False)):
            raise PhysicalTestControlError("PB control return was not committed")

        live_after = await self.control._raw_live()
        lease_after = await self.control._lease_state()
        if not self.control._is_off(live_after):
            raise PhysicalTestControlError(
                "PB control return changed or lost canonical Output OFF"
            )
        if (
            bool(lease_after.armed)
            or bool(lease_after.tripped)
            or bool(lease_after.boot_quarantine)
            or float(lease_after.remaining_s) > 0.0
        ):
            raise PhysicalTestControlError(
                "PB control return changed the clean edge lease state"
            )
        if int(lease_after.generation) != int(lease_before.generation):
            raise PhysicalTestControlError(
                "PB control return unexpectedly changed edge generation"
            )
        if not self._same_programmed_values(programmed_before, live_after):
            raise PhysicalTestControlError(
                "PB control return unexpectedly changed programmed V/I/OVP/OCP"
            )

        return {
            "returned": True,
            "mode": getattr(getattr(manager, "mode", None), "value", getattr(manager, "mode", None)),
            "output": live_after.get("switch"),
            "output_state_code_v2": live_after.get("output_state_code_v2"),
            "generation_before": lease_before.generation,
            "generation_after": lease_after.generation,
            "lease_armed": lease_after.armed,
            "remaining_s": lease_after.remaining_s,
            "programmed_values": programmed_before,
            "hardware_writes_injected": 0,
        }

    async def dispatch(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict) or request.get("op") != _OPERATION:
            return await self._original_dispatch(request)
        try:
            async with self.control._operation_lock:
                self.control._require_fields(request, {"op"})
                result = await self.return_pb_control_verified_off()
            return {"ok": True, "operation": _OPERATION, "result": _json_value(result)}
        except (PhysicalTestControlError, ValueError, TypeError) as exc:
            return self.control._error(str(exc))
        except Exception as exc:
            return self.control._error(
                f"operation rejected: {type(exc).__name__}: {exc}"
            )


def install_physical_test_control_pb_mode(
    app: Any,
    control: PhysicalTestControl,
) -> PhysicalTestControlPbMode:
    """Compose the typed PB-return operation without creating another listener."""

    existing = getattr(app, "physical_test_control_pb_mode", None)
    if isinstance(existing, PhysicalTestControlPbMode):
        return existing
    extension = PhysicalTestControlPbMode(app, control)
    control.dispatch = extension.dispatch
    app.physical_test_control_pb_mode = extension
    return extension
