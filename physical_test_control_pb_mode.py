"""Typed ownership/AUTONOMOUS physical-test transitions on the existing AF_UNIX plane.

The operations are intentionally narrower than the Telegram operator actions: they are
available only while the opt-in physical-test server is enabled, accept no parameters,
require canonical Output OFF plus a clean/readable edge state, and delegate the actual
ownership/operation transition to the already-installed production coordinators. They
never write RD6018 Output/V/I/OVP/OCP directly and never create another listener.
"""
from __future__ import annotations

from typing import Any, Dict

from physical_test_control import PhysicalTestControl, PhysicalTestControlError, _json_value
from rd6018_telemetry import finite_float


_RETURN_PB_OPERATION = "return_pb_control_verified_off"
_AUTONOMOUS_STATUS_OPERATION = "autonomous_status"
_ENTER_AUTONOMOUS_OPERATION = "enter_autonomous_verified_off"
_EXIT_AUTONOMOUS_OPERATION = "exit_autonomous_verified_off"
_AUTONOMOUS_OPERATIONS = {
    _AUTONOMOUS_STATUS_OPERATION,
    _ENTER_AUTONOMOUS_OPERATION,
    _EXIT_AUTONOMOUS_OPERATION,
}
_MAX_MODBUS_AGE_S = 20.0
_PROGRAMMED_KEYS = ("set_voltage", "set_current", "ovp", "ocp")


class PhysicalTestControlPbMode:
    """Strictly typed, OFF-only ownership and AUTONOMOUS validation operations."""

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
                    f"physical ownership transition requires numeric {key} readback"
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

    @staticmethod
    def _protection_normal(live: Dict[str, Any]) -> bool:
        try:
            return int(float(live.get("protection_code"))) == 0
        except (TypeError, ValueError):
            return False

    def _autonomous_coordinator(self) -> Any:
        coordinator = getattr(self.app, "rd_autonomous_mode", None)
        edge = getattr(coordinator, "edge", None)
        if coordinator is None or edge is None:
            raise PhysicalTestControlError("AUTONOMOUS production coordinator unavailable")
        return coordinator

    @staticmethod
    def _manager_mode(manager: Any) -> Any:
        mode = getattr(manager, "mode", None)
        return getattr(mode, "value", mode)

    async def _require_fresh_off_snapshot(self) -> tuple[Dict[str, Any], Any]:
        guard = getattr(self.app, "runtime_safety_guard", None)
        if guard is None:
            raise PhysicalTestControlError("physical transition safety guard unavailable")
        if bool(getattr(guard, "_off_unconfirmed", False)):
            raise PhysicalTestControlError(
                "physical transition blocked while Output OFF remains unconfirmed"
            )
        live = await self.control._raw_live()
        if not self.control._is_off(live):
            raise PhysicalTestControlError(
                "physical transition requires canonical Output OFF / register-18 V2=0"
            )
        if not self._protection_normal(live):
            raise PhysicalTestControlError(
                "physical transition requires authoritative Protection=0"
            )
        lease = await self.control._lease_state()
        try:
            modbus_age_s = float(lease.modbus_age_s)
        except (TypeError, ValueError, AttributeError) as exc:
            raise PhysicalTestControlError(
                "physical transition requires readable direct Modbus age"
            ) from exc
        if modbus_age_s > _MAX_MODBUS_AGE_S:
            raise PhysicalTestControlError(
                "physical transition requires fresh direct Modbus evidence"
            )
        return live, lease

    @staticmethod
    def _require_clean_unmanaged_edge(lease: Any) -> None:
        try:
            remaining_s = float(lease.remaining_s)
            modbus_age_s = float(lease.modbus_age_s)
        except (TypeError, ValueError, AttributeError) as exc:
            raise PhysicalTestControlError(
                "AUTONOMOUS transition requires readable edge lease state"
            ) from exc
        if (
            bool(lease.armed)
            or bool(lease.tripped)
            or bool(lease.boot_quarantine)
            or remaining_s > 0.0
            or modbus_age_s > _MAX_MODBUS_AGE_S
        ):
            raise PhysicalTestControlError(
                "AUTONOMOUS transition requires clean/unarmed edge state and fresh Modbus"
            )

    async def autonomous_status(self) -> Dict[str, Any]:
        coordinator = self._autonomous_coordinator()
        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is None:
            raise PhysicalTestControlError("RD control-mode manager unavailable")
        live = await self.control._raw_live()
        lease = await self.control._lease_state()
        edge_autonomous = bool(await coordinator.edge.read_autonomous())
        return {
            "rd_control_mode": self._manager_mode(manager),
            "manager_edge_autonomous": bool(getattr(manager, "edge_autonomous", False)),
            "edge_autonomous": edge_autonomous,
            "output": live.get("switch"),
            "output_state_code_v2": live.get("output_state_code_v2"),
            "protection_code": live.get("protection_code"),
            "programmed_values": self._programmed_values(live),
            "edge_lease": {
                "armed": lease.armed,
                "tripped": lease.tripped,
                "boot_quarantine": lease.boot_quarantine,
                "generation": lease.generation,
                "remaining_s": lease.remaining_s,
                "modbus_age_s": lease.modbus_age_s,
            },
            "rd_actuator_writes_injected": 0,
        }

    async def enter_autonomous_verified_off(self) -> Dict[str, Any]:
        coordinator = self._autonomous_coordinator()
        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is None:
            raise PhysicalTestControlError("RD control-mode manager unavailable")
        if bool(await coordinator.edge.read_autonomous()):
            raise PhysicalTestControlError(
                "AUTONOMOUS entry validation requires edge AUTONOMOUS initially OFF"
            )
        live_before, lease_before = await self._require_fresh_off_snapshot()
        programmed_before = self._programmed_values(live_before)

        transition = getattr(coordinator, "enter", None)
        if not callable(transition):
            raise PhysicalTestControlError("AUTONOMOUS enter API unavailable")
        entered = bool(await transition())
        if not entered:
            raise PhysicalTestControlError("AUTONOMOUS entry was not committed")

        live_after, lease_after = await self._require_fresh_off_snapshot()
        self._require_clean_unmanaged_edge(lease_after)
        edge_after = bool(await coordinator.edge.read_autonomous())
        if not edge_after or not bool(getattr(manager, "edge_autonomous", False)):
            raise PhysicalTestControlError(
                "AUTONOMOUS entry lacks positive edge/manager authority evidence"
            )
        if not bool(getattr(manager, "hands_off", False)):
            raise PhysicalTestControlError(
                "AUTONOMOUS entry did not preserve the software HANDS_OFF boundary"
            )
        if int(lease_after.generation) == int(lease_before.generation):
            raise PhysicalTestControlError(
                "AUTONOMOUS entry did not advance edge generation"
            )
        if not self._same_programmed_values(programmed_before, live_after):
            raise PhysicalTestControlError(
                "AUTONOMOUS entry unexpectedly changed programmed V/I/OVP/OCP"
            )
        return {
            "entered": True,
            "rd_control_mode": self._manager_mode(manager),
            "edge_autonomous": edge_after,
            "output": live_after.get("switch"),
            "output_state_code_v2": live_after.get("output_state_code_v2"),
            "generation_before": lease_before.generation,
            "generation_after": lease_after.generation,
            "lease_armed": lease_after.armed,
            "remaining_s": lease_after.remaining_s,
            "programmed_values": programmed_before,
            "rd_actuator_writes_injected": 0,
        }

    async def exit_autonomous_verified_off(self) -> Dict[str, Any]:
        coordinator = self._autonomous_coordinator()
        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is None:
            raise PhysicalTestControlError("RD control-mode manager unavailable")
        if not bool(await coordinator.edge.read_autonomous()):
            raise PhysicalTestControlError(
                "AUTONOMOUS exit validation requires edge AUTONOMOUS initially ON"
            )
        live_before, lease_before = await self._require_fresh_off_snapshot()
        self._require_clean_unmanaged_edge(lease_before)
        programmed_before = self._programmed_values(live_before)

        transition = getattr(coordinator, "exit", None)
        if not callable(transition):
            raise PhysicalTestControlError("AUTONOMOUS exit API unavailable")
        exited = bool(await transition())
        if not exited:
            raise PhysicalTestControlError("AUTONOMOUS exit was not committed")

        live_after, lease_after = await self._require_fresh_off_snapshot()
        self._require_clean_unmanaged_edge(lease_after)
        edge_after = bool(await coordinator.edge.read_autonomous())
        if edge_after or bool(getattr(manager, "edge_autonomous", False)):
            raise PhysicalTestControlError(
                "AUTONOMOUS exit did not clear edge/manager authority"
            )
        if not bool(getattr(manager, "pb_managed", False)):
            raise PhysicalTestControlError(
                "AUTONOMOUS exit did not return software ownership to PB_MANAGED"
            )
        if int(lease_after.generation) == int(lease_before.generation):
            raise PhysicalTestControlError(
                "AUTONOMOUS exit did not advance edge generation"
            )
        if not self._same_programmed_values(programmed_before, live_after):
            raise PhysicalTestControlError(
                "AUTONOMOUS exit unexpectedly changed programmed V/I/OVP/OCP"
            )
        return {
            "exited": True,
            "rd_control_mode": self._manager_mode(manager),
            "edge_autonomous": edge_after,
            "output": live_after.get("switch"),
            "output_state_code_v2": live_after.get("output_state_code_v2"),
            "generation_before": lease_before.generation,
            "generation_after": lease_after.generation,
            "lease_armed": lease_after.armed,
            "remaining_s": lease_after.remaining_s,
            "programmed_values": programmed_before,
            "rd_actuator_writes_injected": 0,
        }

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
        if not isinstance(request, dict):
            return await self._original_dispatch(request)
        operation = request.get("op")
        if operation not in ({_RETURN_PB_OPERATION} | _AUTONOMOUS_OPERATIONS):
            return await self._original_dispatch(request)
        try:
            async with self.control._operation_lock:
                self.control._require_fields(request, {"op"})
                if operation == _RETURN_PB_OPERATION:
                    result = await self.return_pb_control_verified_off()
                elif operation == _AUTONOMOUS_STATUS_OPERATION:
                    result = await self.autonomous_status()
                elif operation == _ENTER_AUTONOMOUS_OPERATION:
                    result = await self.enter_autonomous_verified_off()
                else:
                    result = await self.exit_autonomous_verified_off()
            return {"ok": True, "operation": operation, "result": _json_value(result)}
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
    """Compose typed ownership operations without creating another listener."""

    existing = getattr(app, "physical_test_control_pb_mode", None)
    if isinstance(existing, PhysicalTestControlPbMode):
        return existing
    extension = PhysicalTestControlPbMode(app, control)
    control.dispatch = extension.dispatch
    app.physical_test_control_pb_mode = extension
    return extension
