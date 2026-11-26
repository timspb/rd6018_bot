"""Behavioral contract for the production data_logger recovery barrier."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from application.execution_port import ExecutionPort
from application.session_recovery_guard import SessionRecoveryGuard
from production_controller import create_production_charge_host
from runtime.production_runtime import data_logger
import runtime.production_runtime as production_runtime


class _StopAfterOneCycle(Exception):
    pass


class DataLoggerRecoveryQuarantineTests(unittest.IsolatedAsyncioTestCase):
    async def _run_one_cycle(self, *, quarantined, guard=None, live_overrides=None):
        guard = guard or SessionRecoveryGuard()
        controller = create_production_charge_host(object())
        if quarantined:
            # Reproduce the failure boundary established by AD153: restoration
            # mutates the host, then raises, and lifecycle latches this guard.
            try:
                controller.current_stage = controller.STAGE_MAIN
                raise RuntimeError("injected late restore failure")
            except RuntimeError as exc:
                guard.quarantine("startup_restore_failed:" + type(exc).__name__)
        stage_before = controller.current_stage

        live = {
            "battery_voltage": 12.5, "voltage": 0.0, "current": 0.0,
            "power": 0.0, "temp_ext": 25.0, "ah": 0.0,
            "switch": "off", "battery_mode": "off", "input_voltage": 0.0,
            "temp_int": 25.0, "set_voltage": 0.0, "set_current": 0.0,
            "is_cv": False, "is_cc": False,
        }
        live.update(live_overrides or {})
        owner = SimpleNamespace(
            get_all_live=AsyncMock(return_value=live),
            safe_enable_output=AsyncMock(),
            turn_on=AsyncMock(), set_voltage=AsyncMock(), set_current=AsyncMock(),
        )
        port = ExecutionPort(owner, guard, app=production_runtime)
        original_tick = production_runtime.run_charge_session_tick
        tick = AsyncMock(wraps=original_tick)

        patches = {
            # Managed live reads must stay on the installed safety owner.
            # A direct HassClient read here would bypass native provenance and
            # the managed recovery barrier.
            "hass": SimpleNamespace(
                get_all_live=AsyncMock(side_effect=AssertionError("direct HassClient read")),
            ),
            "runtime_safety_guard": owner,
            "session_recovery_guard": guard,
            "execution_port": port,
            "charge_controller": controller,
            "_operator_pause_active": Mock(return_value=False),
            "_has_manual_off_condition": Mock(return_value=False),
            "_sync_total_start_from_uptime": Mock(),
            "_log_temperature_source_if_changed": Mock(),
            "dispatch_live_protection": AsyncMock(),
            "read_canonical_session": Mock(return_value=None),
            "admit_main_guard_shadow": Mock(return_value=None),
            "add_record": AsyncMock(),
            "run_charge_session_tick": tick,
            "last_checkpoint_time": 1000.0,
        }
        add_record = patches["add_record"]
        with patch.multiple(production_runtime, create=True, **patches), \
             patch.object(production_runtime.time, "time", return_value=1000.0), \
             patch.object(production_runtime, "log_event", Mock()), \
             patch.object(production_runtime, "log_checkpoint", Mock()), \
             patch.object(production_runtime, "_charge_notify", Mock()), \
             patch.object(production_runtime.asyncio, "sleep", side_effect=_StopAfterOneCycle):
            try:
                await data_logger()
            except _StopAfterOneCycle:
                pass

        return guard, controller, stage_before, tick, owner, add_record

    async def test_failed_restore_quarantine_suppresses_actual_data_logger_tick(self):
        guard, controller, stage_before, tick, owner, _ = await self._run_one_cycle(
            quarantined=True,
        )

        self.assertTrue(guard.quarantined)
        self.assertEqual(guard.state.reason, "startup_restore_failed:RuntimeError")
        tick.assert_not_awaited()
        self.assertEqual(controller.current_stage, stage_before)
        owner.safe_enable_output.assert_not_awaited()
        owner.turn_on.assert_not_awaited()
        owner.set_voltage.assert_not_awaited()
        owner.set_current.assert_not_awaited()

    async def test_clear_guard_runs_the_normal_data_logger_tick_once(self):
        guard, controller, stage_before, tick, owner, _ = await self._run_one_cycle(
            quarantined=False,
        )

        self.assertFalse(guard.quarantined)
        tick.assert_awaited_once()
        self.assertEqual(controller.current_stage, stage_before)
        owner.safe_enable_output.assert_not_awaited()
        owner.turn_on.assert_not_awaited()
        owner.set_voltage.assert_not_awaited()
        owner.set_current.assert_not_awaited()

    async def test_native_recovery_markers_defer_cycle_without_output_or_setpoint_writes(self):
        # Presence of the native outage marker remains conservative even when
        # its value/provenance is unknown or malformed. The explicit managed
        # pending marker has the same tick-suppression effect.
        recovery_observations = (
            {"_native_link_outage_since": None,
             "_meta": {"switch": {"source": "unknown", "status": "invalid"}}},
            {"_native_link_outage_since": "malformed"},
            {"_managed_telemetry_recovery_pending": True,
             "_meta": {"switch": {"source": "esp_native_api", "status": "stale"}}},
        )
        for live in recovery_observations:
            with self.subTest(live=live):
                guard, controller, _, tick, owner, add_record = await self._run_one_cycle(
                    quarantined=False,
                    live_overrides=live,
                )

                self.assertFalse(guard.quarantined)
                tick.assert_not_awaited()
                add_record.assert_not_awaited()
                owner.get_all_live.assert_awaited_once()
                owner.safe_enable_output.assert_not_awaited()
                owner.turn_on.assert_not_awaited()
                owner.set_voltage.assert_not_awaited()
                owner.set_current.assert_not_awaited()
                self.assertIsNone(getattr(controller, "_device_set_voltage", None))
                self.assertIsNone(getattr(controller, "_device_set_current", None))

    def test_data_logger_keeps_one_lifecycle_loop_and_no_private_timing_task(self):
        import ast
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "runtime" / "production_runtime.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        logger = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "data_logger"
        )
        loops = [node for node in ast.walk(logger) if isinstance(node, ast.While)]
        self.assertEqual(len(loops), 1)
        self.assertFalse(any(
            isinstance(node, ast.Call)
            and ast.unparse(node.func) in {"asyncio.create_task", "asyncio.ensure_future"}
            for node in ast.walk(logger)
        ))


if __name__ == "__main__":
    unittest.main()
