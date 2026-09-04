"""Typed D041/D051 diagnostic physical-test hooks on the existing AF_UNIX plane."""
from __future__ import annotations

import asyncio
import re
from types import MethodType
from typing import Any, Dict, Optional

from battery_registry import get_battery
from diagnostic_persistence import (
    DiagnosticActionKind,
    DiagnosticActionStatus,
    PersistentControlledCurrentProbe,
)
from diagnostic_probe import ProbePlan
from manual_mode import ManualChargeRequest
from pb_domain import BatteryChemistry
from physical_test_control import PhysicalTestControl, PhysicalTestControlError, _json_value
from rd6018_telemetry import finite_float

_OPS = {"diagnostic_probe_cancel_after_step", "diagnostic_probe_prepare_restart_window"}
_BATTERY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MANUAL_V = 14.00
_MANUAL_I = 0.30
_STEP_I = 0.20
_I_TOL = 0.06
_MAX_TEMP_C = 35.0
_STEP_TIMEOUT_S = 12.0
_RESTART_WINDOW_S = 20.0


class PhysicalTestControlDiagnostic:
    def __init__(self, app: Any, control: PhysicalTestControl) -> None:
        self.app = app
        self.control = control
        self._original_dispatch = control.dispatch
        self._restart_probe_task: Optional[asyncio.Task[Any]] = None
        self._restart_cleanup_task: Optional[asyncio.Task[Any]] = None

    @staticmethod
    def _inactive(obj: Any) -> bool:
        return not bool(getattr(obj, "active", False)) and not bool(
            getattr(obj, "is_active", False)
        ) and not bool(getattr(obj, "off_pending", False))

    async def _battery_id(self, value: Any) -> str:
        if not isinstance(value, str):
            raise PhysicalTestControlError("battery_id is invalid")
        battery_id = value.strip()
        if not _BATTERY_ID_RE.fullmatch(battery_id):
            raise PhysicalTestControlError("battery_id is invalid")
        record = await get_battery(battery_id)
        chemistry = getattr(getattr(record, "identity", None), "chemistry", None)
        if record is None or chemistry is None or chemistry is BatteryChemistry.CUSTOM:
            raise PhysicalTestControlError("diagnostic test requires a saved non-CUSTOM Pb battery")
        return battery_id

    async def _safe_initial(self) -> Any:
        mode = getattr(self.app, "rd_control_mode_manager", None)
        if mode is None or not bool(getattr(mode, "hands_off", False)):
            raise PhysicalTestControlError("diagnostic test requires HANDS_OFF")
        if bool(getattr(mode, "release_in_progress", False)):
            raise PhysicalTestControlError("diagnostic test blocked during ownership transfer")
        for name in (
            "charge_controller",
            "manual_session_manager",
            "rd_managed_live_adoption",
            "rd_managed_mix_adoption",
        ):
            if not self._inactive(getattr(self.app, name, None)):
                raise PhysicalTestControlError(f"diagnostic test requires idle {name}")
        live = await self.control._raw_live()
        if not self.control._is_off(live):
            raise PhysicalTestControlError("diagnostic test requires canonical Output OFF")
        try:
            protection = int(float(live.get("protection_code")))
        except (TypeError, ValueError) as exc:
            raise PhysicalTestControlError("raw protection_code is unavailable") from exc
        if protection != 0:
            raise PhysicalTestControlError("diagnostic test requires Protection=0")
        temp = finite_float(live.get("temp_ext"))
        if temp is None or temp >= _MAX_TEMP_C:
            raise PhysicalTestControlError("diagnostic test requires battery temperature <35C")
        lease = await self.control._lease_state()
        if (
            bool(lease.armed)
            or bool(lease.tripped)
            or bool(lease.boot_quarantine)
            or float(lease.modbus_age_s) > 20.0
        ):
            raise PhysicalTestControlError("diagnostic test requires clean/fresh edge lease state")
        return lease

    async def _enter_hands_off_if_safe(self) -> None:
        mode = self.app.rd_control_mode_manager
        manual = self.app.manual_session_manager
        if bool(getattr(mode, "hands_off", False)) or bool(getattr(manual, "is_active", False)):
            return
        if self.control._is_off(await self.control._raw_live()):
            await mode.enter_hands_off()

    async def _stop_and_hands_off(self, reason: str) -> None:
        manual = self.app.manual_session_manager
        if bool(getattr(manual, "is_active", False)):
            if not bool(await manual.stop(reason)):
                raise PhysicalTestControlError("temporary Manual Output OFF was not confirmed")
        live = await self.control._raw_live()
        lease = await self.control._lease_state()
        if not self.control._is_off(live):
            raise PhysicalTestControlError("cleanup did not confirm canonical Output OFF")
        if bool(lease.armed):
            raise PhysicalTestControlError("cleanup left edge lease armed")
        await self._enter_hands_off_if_safe()

    async def _start_manual(self, battery_id_raw: Any) -> tuple[str, Any]:
        battery_id = await self._battery_id(battery_id_raw)
        lease_before = await self._safe_initial()
        mode = self.app.rd_control_mode_manager
        if not bool(await mode.return_pb_control()):
            raise PhysicalTestControlError("could not enter PB_MANAGED")
        manual = self.app.manual_session_manager
        started = False
        try:
            request = ManualChargeRequest(
                voltage_v=_MANUAL_V,
                current_a=_MANUAL_I,
                battery_id=battery_id,
                notes="physical-test:diagnostic-probe",
            )
            started = bool(await manual.start(request))
            if not started:
                raise PhysicalTestControlError("temporary Manual start was denied")
            live = await self.control._raw_live()
            lease = await self.control._lease_state()
            set_v = finite_float(live.get("set_voltage"))
            set_i = finite_float(live.get("set_current"))
            ovp = finite_float(live.get("ovp"))
            ocp = finite_float(live.get("ocp"))
            if not self.control._is_on(live) or not bool(lease.armed):
                raise PhysicalTestControlError("temporary Manual was not positively ON/leased")
            if (
                set_v is None
                or set_i is None
                or ovp is None
                or ocp is None
                or abs(set_v - _MANUAL_V) > 0.08
                or abs(set_i - _MANUAL_I) > _I_TOL
                or ovp > 14.20
                or ocp > 0.50
            ):
                raise PhysicalTestControlError("temporary Manual exceeded hard-coded envelope")
            return battery_id, lease_before
        except BaseException:
            try:
                if started or bool(getattr(manual, "is_active", False)):
                    await asyncio.shield(self._stop_and_hands_off("physical_test_setup_failed"))
                else:
                    await asyncio.shield(self._enter_hands_off_if_safe())
            except BaseException:
                pass
            raise

    @staticmethod
    def _plan() -> ProbePlan:
        return ProbePlan(
            step_current_a=_STEP_I,
            settle_s=0.0,
            sample_count=2,
            sample_interval_s=0.05,
            readback_tolerance_a=_I_TOL,
            max_battery_temp_c=_MAX_TEMP_C,
        )

    def _make_probe(self, event: asyncio.Event) -> PersistentControlledCurrentProbe:
        journal = getattr(self.app, "diagnostic_action_journal", None)
        if journal is None:
            raise PhysicalTestControlError("diagnostic action journal unavailable")
        probe = PersistentControlledCurrentProbe(self.app.hass, journal)
        original = probe._sample_medians
        hold = asyncio.Event()
        calls = 0

        async def blocked(_self: Any, plan: ProbePlan) -> tuple[float, float]:
            nonlocal calls
            calls += 1
            if calls == 1:
                return await original(plan)
            event.set()
            await hold.wait()
            return await original(plan)

        probe._sample_medians = MethodType(blocked, probe)
        return probe

    def _spawn_probe(self, battery_id: str, event: asyncio.Event, *, restart: bool) -> asyncio.Task[Any]:
        probe = self._make_probe(event)
        suffix = "restart" if restart else "cancel"
        return asyncio.create_task(
            probe.run(
                battery_id=battery_id,
                stage="physical-test-diagnostic",
                connection_id=f"physical-test-diagnostic-{suffix}",
                plan=self._plan(),
                notes=f"physical-test diagnostic {suffix} gate",
            ),
            name=f"physical-test-diagnostic-{suffix}",
        )

    async def _wait_step(self, task: asyncio.Task[Any], event: asyncio.Event) -> tuple[Dict[str, Any], Any]:
        waiter = asyncio.create_task(event.wait())
        try:
            done, _ = await asyncio.wait(
                {task, waiter}, timeout=_STEP_TIMEOUT_S, return_when=asyncio.FIRST_COMPLETED
            )
            if waiter not in done or not event.is_set():
                if task in done:
                    try:
                        value = task.result()
                    except BaseException as exc:
                        raise PhysicalTestControlError(
                            f"probe failed before step hold: {type(exc).__name__}: {exc}"
                        ) from exc
                    raise PhysicalTestControlError(f"probe ended before step hold: {value!r}")
                raise PhysicalTestControlError("probe timed out before safer current step")
        finally:
            if not waiter.done():
                waiter.cancel()
            try:
                await waiter
            except BaseException:
                pass
        live = await self.control._raw_live()
        lease = await self.control._lease_state()
        set_i = finite_float(live.get("set_current"))
        if (
            not self.control._is_on(live)
            or set_i is None
            or abs(set_i - _STEP_I) > _I_TOL
            or not bool(lease.armed)
        ):
            raise PhysicalTestControlError("safer diagnostic current step was not positively active")
        return live, lease

    def _latest_probe(self, battery_id: str) -> Any:
        journal = self.app.diagnostic_action_journal
        rows = [
            row
            for row in journal.records
            if row.kind is DiagnosticActionKind.PROBE and row.battery_id == battery_id
        ]
        return rows[-1] if rows else None

    async def cancel_after_step(self, battery_id_raw: Any) -> Dict[str, Any]:
        if self._restart_probe_task is not None and not self._restart_probe_task.done():
            raise PhysicalTestControlError("restart window is already active")
        battery_id, before = await self._start_manual(battery_id_raw)
        event = asyncio.Event()
        task: Optional[asyncio.Task[Any]] = None
        step_lease = None
        cleanup_error = None
        restored_before_off = False
        try:
            task = self._spawn_probe(battery_id, event, restart=False)
            _step_live, step_lease = await self._wait_step(task, event)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            live = await self.control._raw_live()
            set_i = finite_float(live.get("set_current"))
            restored_before_off = bool(
                self.control._is_on(live)
                and set_i is not None
                and abs(set_i - _MANUAL_I) <= _I_TOL
            )
            if not restored_before_off:
                raise PhysicalTestControlError("probe cancellation did not restore 0.30A while ON")
            record = self._latest_probe(battery_id)
            if record is None or record.status is not DiagnosticActionStatus.FAILED:
                raise PhysicalTestControlError("cancelled probe action was not durably retired")
        finally:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
            try:
                await asyncio.shield(self._stop_and_hands_off("physical_test_diagnostic_cancel"))
            except BaseException as exc:
                cleanup_error = exc
        if cleanup_error is not None:
            raise PhysicalTestControlError(f"diagnostic cancellation cleanup failed: {cleanup_error}")
        final = await self.control._raw_live()
        after = await self.control._lease_state()
        return {
            "cancelled": True,
            "battery_id": battery_id,
            "manual_voltage_v": _MANUAL_V,
            "manual_current_a": _MANUAL_I,
            "probe_step_current_a": _STEP_I,
            "original_current_restored_before_off": restored_before_off,
            "generation_before": before.generation,
            "generation_step": None if step_lease is None else step_lease.generation,
            "generation_after": after.generation,
            "output": final.get("switch"),
            "output_state_code_v2": final.get("output_state_code_v2"),
            "lease_armed": after.armed,
            "remaining_s": after.remaining_s,
        }

    async def _deadline_cleanup(self, task: asyncio.Task[Any]) -> None:
        try:
            await asyncio.sleep(_RESTART_WINDOW_S)
        except asyncio.CancelledError:
            pass
        try:
            if not task.done():
                task.cancel()
            try:
                await task
            except BaseException:
                pass
            await asyncio.shield(self._stop_and_hands_off("physical_test_restart_window_expired"))
        finally:
            self._restart_probe_task = None
            self._restart_cleanup_task = None

    async def prepare_restart_window(self, battery_id_raw: Any) -> Dict[str, Any]:
        if self._restart_probe_task is not None and not self._restart_probe_task.done():
            raise PhysicalTestControlError("restart window is already active")
        battery_id, before = await self._start_manual(battery_id_raw)
        event = asyncio.Event()
        task: Optional[asyncio.Task[Any]] = None
        try:
            task = self._spawn_probe(battery_id, event, restart=True)
            live, lease = await self._wait_step(task, event)
            record = self._latest_probe(battery_id)
            if record is None or record.status is not DiagnosticActionStatus.RUNNING:
                raise PhysicalTestControlError("restart gate requires durable RUNNING probe journal")
        except BaseException:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
            try:
                await asyncio.shield(self._stop_and_hands_off("physical_test_restart_prepare_failed"))
            except BaseException:
                pass
            raise
        self._restart_probe_task = task
        self._restart_cleanup_task = asyncio.create_task(
            self._deadline_cleanup(task), name="physical-test-diagnostic-restart-deadline"
        )
        return {
            "ready_for_sigkill": True,
            "battery_id": battery_id,
            "action_id": record.action_id,
            "journal_status": record.status.value,
            "restart_window_s": _RESTART_WINDOW_S,
            "manual_voltage_v": _MANUAL_V,
            "manual_current_a": _MANUAL_I,
            "probe_step_current_a": _STEP_I,
            "set_current": live.get("set_current"),
            "output": live.get("switch"),
            "output_state_code_v2": live.get("output_state_code_v2"),
            "lease_armed": lease.armed,
            "remaining_s": lease.remaining_s,
            "generation_before": before.generation,
            "generation_ready": lease.generation,
            "instruction": "SIGKILL bot.py now; graceful restart is not this test",
        }

    async def dispatch(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict) or request.get("op") not in _OPS:
            return await self._original_dispatch(request)
        op = request["op"]
        try:
            async with self.control._operation_lock:
                self.control._require_fields(request, {"op", "battery_id"})
                result = (
                    await self.cancel_after_step(request["battery_id"])
                    if op == "diagnostic_probe_cancel_after_step"
                    else await self.prepare_restart_window(request["battery_id"])
                )
            return {"ok": True, "operation": op, "result": _json_value(result)}
        except (PhysicalTestControlError, ValueError, TypeError) as exc:
            return self.control._error(str(exc))
        except Exception as exc:
            return self.control._error(f"operation rejected: {type(exc).__name__}: {exc}")


def install_physical_test_control_diagnostic(
    app: Any, control: PhysicalTestControl
) -> PhysicalTestControlDiagnostic:
    existing = getattr(app, "physical_test_control_diagnostic", None)
    if isinstance(existing, PhysicalTestControlDiagnostic):
        return existing
    extension = PhysicalTestControlDiagnostic(app, control)
    control.dispatch = extension.dispatch
    app.physical_test_control_diagnostic = extension
    return extension
