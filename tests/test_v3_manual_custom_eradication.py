import os
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from charge_controller import ManagedChargeController
from manual_runtime import ProductionManualSessionManager


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class DummyHass:
    pass


class DummyController:
    is_active = False


class V3ManualCustomEradicationTests(unittest.IsolatedAsyncioTestCase):
    def test_production_controller_rejects_historical_custom_start(self):
        controller = ManagedChargeController(DummyHass())

        self.assertFalse(hasattr(controller, "start_custom"))

        with self.assertRaisesRegex(RuntimeError, "historical Custom controller start is retired"):
            controller.start(controller.PROFILE_CUSTOM, 70)

        self.assertFalse(controller.is_active)
        self.assertEqual(controller.current_stage, controller.STAGE_IDLE)

    async def test_authoritative_custom_state_never_enters_historical_tick(self):
        controller = ManagedChargeController(DummyHass())
        controller.battery_type = controller.PROFILE_CUSTOM
        controller.ah_capacity = 70
        controller.current_stage = controller.STAGE_MAIN

        actions = await controller._run_stage_scaffold_tick(
            stage_before=controller.STAGE_MAIN,
            voltage=14.8,
            current=2.0,
            temp_ext=25.0,
            is_cv=True,
            ah=1.0,
            output_is_on=True,
            manual_off_active=False,
            is_cc=False,
            manual_active=False,
        )

        self.assertTrue(actions.get("turn_off"))
        self.assertEqual(
            actions.get("log_event"),
            "HISTORICAL_CUSTOM_RUNTIME_RETIRED",
        )
        self.assertEqual(controller.current_stage, controller.STAGE_IDLE)

    async def test_idle_custom_residue_is_inert_and_never_enters_historical_tick(self):
        controller = ManagedChargeController(DummyHass())
        controller.battery_type = controller.PROFILE_CUSTOM
        controller.current_stage = controller.STAGE_IDLE

        actions = await controller._run_stage_scaffold_tick(
            stage_before=controller.STAGE_IDLE,
            voltage=0.0,
            current=0.0,
            temp_ext=25.0,
            is_cv=False,
            ah=0.0,
            output_is_on=False,
            manual_off_active=False,
            is_cc=False,
            manual_active=True,
        )

        self.assertEqual(actions, {})
        self.assertEqual(controller.current_stage, controller.STAGE_IDLE)

    def test_authoritative_restore_rejects_and_clears_historical_custom_session(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            with patch("charge_controller.SESSION_FILE", session_file), patch(
                "charge_controller.time.time", return_value=1000.0
            ):
                legacy = ManagedChargeController(DummyHass())
                legacy.start(legacy.PROFILE_EFB, 70)
                legacy.battery_type = legacy.PROFILE_CUSTOM
                legacy.current_stage = legacy.STAGE_MAIN
                legacy._custom_main_voltage = 14.8
                legacy._custom_main_current = 5.0
                legacy._custom_delta_threshold = 0.03
                legacy._custom_time_limit_hours = 24.0
                legacy._device_set_voltage = 14.8
                legacy._device_set_current = 5.0
                legacy._save_session(14.2, 1.0, 1.0)
                self.assertTrue(os.path.exists(session_file))

            with patch("charge_controller.SESSION_FILE", session_file), patch(
                "charge_controller.time.time", return_value=1100.0
            ):
                production = ManagedChargeController(DummyHass())
                ok, message = production.try_restore_session(14.2, 1.0, 1.0)

            self.assertFalse(ok)
            self.assertIn("Manual", message or "")
            self.assertEqual(production.current_stage, production.STAGE_IDLE)
            self.assertFalse(production.is_active)
            self.assertFalse(os.path.exists(session_file))

    def test_raw_legacy_custom_entrypoint_has_no_actuator_or_historical_fsm_calls(self):
        source = (REPO_ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        start = source.index("async def start_custom_charge")
        end = source.index("def _cancel_custom_mode_state", start)
        body = source[start:end]

        self.assertIn("manual_session_manager", body)
        self.assertIn("start_from_legacy_ui", body)
        for forbidden in (
            "charge_controller.start_custom(",
            "hass.set_ovp(",
            "hass.set_ocp(",
            "hass.set_voltage(",
            "hass.set_current(",
            "hass.turn_on(",
            "safe_enable_output(",
        ):
            self.assertNotIn(forbidden, body)

    def test_production_bootstrap_binds_custom_dialog_to_manual_owner(self):
        source = (REPO_ROOT / "production_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn(
            "app.start_custom_charge = app.manual_session_manager.start_from_legacy_ui",
            source,
        )

    async def test_legacy_five_step_payload_preserves_semantics_in_manual_request(self):
        app = SimpleNamespace(
            hass=DummyHass(),
            charge_controller=DummyController(),
            last_chat_id=0,
            last_user_id=0,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            manager = ProductionManualSessionManager(
                app,
                session_file=os.path.join(tempdir, "manual.json"),
            )
            manager.start = AsyncMock(return_value=True)
            message = SimpleNamespace(
                chat=SimpleNamespace(id=123),
                from_user=SimpleNamespace(id=456),
                answer=AsyncMock(),
            )
            params = {
                "main_voltage": 14.9,
                "main_current": 4.5,
                "delta": 0.025,
                "time_limit": 18.0,
                "capacity": 82.0,
            }

            await manager.start_from_legacy_ui(message, 456, params)

            manager.start.assert_awaited_once()
            request = manager.start.await_args.args[0]
            self.assertAlmostEqual(request.voltage_v, 14.9)
            self.assertAlmostEqual(request.current_a, 4.5)
            self.assertAlmostEqual(request.stop.delta or 0.0, 0.025)
            self.assertAlmostEqual(request.stop.max_active_seconds or 0.0, 18.0 * 3600.0)
            self.assertAlmostEqual(request.capacity_ah or 0.0, 82.0)
            self.assertEqual(request.notes, "legacy Custom UI compatibility adapter")
            self.assertEqual(app.last_chat_id, 123)
            self.assertEqual(app.last_user_id, 456)
            self.assertGreaterEqual(message.answer.await_count, 1)


if __name__ == "__main__":
    unittest.main()
