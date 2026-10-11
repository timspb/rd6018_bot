import os
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from charge_controller import ManagedChargeController
from manual_mode import ManualUIIntent
from manual_runtime import ProductionManualSessionManager, ProductionManualUIRoute

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

    def test_runtime_has_no_retired_ui_adapter_or_monkeypatch(self):
        runtime_source = (REPO_ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        bootstrap_source = (REPO_ROOT / "production_bootstrap.py").read_text(encoding="utf-8")
        manual_source = (REPO_ROOT / "manual_mode.py").read_text(encoding="utf-8")
        self.assertNotIn("start_from_legacy_ui", runtime_source + bootstrap_source + manual_source)
        self.assertNotIn("app.start_custom_charge", bootstrap_source)
        self.assertIn("ManualUIIntent", runtime_source)
        self.assertIn("ProductionManualUIRoute", bootstrap_source)

    async def test_approved_typed_intent_reaches_canonical_manager_only(self):
        app = SimpleNamespace(hass=DummyHass(), charge_controller=DummyController(), last_chat_id=0, last_user_id=0)
        with tempfile.TemporaryDirectory() as tempdir:
            manager = ProductionManualSessionManager(app, session_file=os.path.join(tempdir, "manual.json"))
            manager.start = AsyncMock(return_value=True)
            route = ProductionManualUIRoute(manager)
            intent = ManualUIIntent.from_dialog(
                user_id=456, chat_id=123,
                params={"main_voltage": 14.9, "main_current": 4.5, "delta": 0.025, "time_limit": 18.0, "capacity": 82.0},
            )
            result = await route.submit(intent)
            self.assertTrue(result.accepted)
            manager.start.assert_awaited_once_with(result.request)
            self.assertEqual(result.request.stop.max_active_seconds, 18.0 * 3600.0)
            self.assertEqual(app.last_chat_id, 123)
            self.assertEqual(app.last_user_id, 456)

    async def test_rejected_typed_intent_is_fail_closed_without_actuation(self):
        app = SimpleNamespace(hass=DummyHass(), charge_controller=DummyController(), last_chat_id=0, last_user_id=0)
        with tempfile.TemporaryDirectory() as tempdir:
            manager = ProductionManualSessionManager(app, session_file=os.path.join(tempdir, "manual.json"))
            manager.start = AsyncMock(return_value=True)
            route = ProductionManualUIRoute(manager)
            with self.assertRaises(ValueError):
                ManualUIIntent.from_dialog(
                    user_id=456, chat_id=123,
                    params={"main_voltage": 17.1, "main_current": 4.5, "delta": 0.025, "time_limit": 18.0, "capacity": 82.0},
                )
            manager.start.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
