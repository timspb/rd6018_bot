import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

import bot
from manual_context_v2 import BoundManualTextMiddleware
from manual_mode import ManualSessionState
from manual_runtime_v2 import ProductionManualSessionManager
from manual_text_v2 import ManualTextMiddleware


class ManualContextEntrypointTests(unittest.TestCase):
    def test_program_menu_routes_manual_through_identity_choice(self) -> None:
        keyboard = bot._build_charge_modes_keyboard()
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("v2_manual_choose", callbacks)
        self.assertNotIn("v2_manual", callbacks)

    def test_context_callbacks_are_registered(self) -> None:
        handlers = bot.router.observers["callback_query"].handlers
        names = {handler.callback.__name__ for handler in handlers}
        self.assertIn("_manual_choose", names)
        self.assertIn("_manual_bind", names)
        self.assertIn("_manual_interrupted", names)
        self.assertIn("_manual_reauthorize", names)
        self.assertIn("_manual_discard", names)

    def test_battery_bound_manual_middleware_precedes_generic_numeric_parser(self) -> None:
        manager = bot.router.observers["message"].outer_middleware
        middlewares = list(manager._middlewares)
        bound_index = next(
            index for index, middleware in enumerate(middlewares)
            if isinstance(middleware, BoundManualTextMiddleware)
        )
        generic_index = next(
            index for index, middleware in enumerate(middlewares)
            if isinstance(middleware, ManualTextMiddleware)
        )
        self.assertLess(
            bound_index,
            generic_index,
            "battery-bound Manual must own the numeric payload before generic V I parsing",
        )


class _FakeHass:
    def __init__(self) -> None:
        self.safe_enable_calls = []
        self.turn_off_calls = 0

    async def safe_enable_output(self, **kwargs):
        self.safe_enable_calls.append(kwargs)
        return SimpleNamespace(enabled=True, detail="")

    async def turn_off(self):
        self.turn_off_calls += 1
        return True

    async def get_all_live(self):
        return {
            "temp_ext": 25.0,
            "battery_voltage": 12.8,
            "current": 1.0,
            "switch": "on",
        }


class _FakeController:
    is_active = False


class _FakeApp:
    def __init__(self) -> None:
        self.hass = _FakeHass()
        self.charge_controller = _FakeController()


class ManualInterruptedReauthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_battery_identity_survives_restart_but_output_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "manual_session.json")
            old_started = 100.0
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": 2,
                        "state": "active",
                        "request": {
                            "voltage_v": 14.7,
                            "current_a": 5.0,
                            "stop": {
                                "max_active_seconds": 7200.0,
                                "voltage_ge_v": None,
                                "voltage_le_v": None,
                                "current_ge_a": None,
                                "current_le_a": 0.3,
                                "delta": None,
                            },
                            "battery_id": "physical-battery-1",
                            "capacity_ah": None,
                            "notes": "saved manual",
                        },
                        "started_at": old_started,
                        "paused_total_s": 0.0,
                        "cooling_started_at": None,
                        "stop_reason": "",
                        "saved_at": 101.0,
                        "reach_voltage_v": 15.2,
                        "reach_current_a": None,
                    },
                    handle,
                )

            app = _FakeApp()
            manager = ProductionManualSessionManager(app, session_file=path)

            self.assertEqual(manager.state, ManualSessionState.INTERRUPTED)
            self.assertEqual(manager.request.battery_id, "physical-battery-1")
            self.assertEqual(manager.reach_voltage_v, 15.2)
            self.assertEqual(app.hass.safe_enable_calls, [])

            before = time.time()
            enabled = await manager.start(
                manager.request,
                reach_voltage_v=manager.reach_voltage_v,
                reach_current_a=manager.reach_current_a,
            )
            self.assertTrue(enabled)
            self.assertEqual(manager.state, ManualSessionState.ACTIVE)
            self.assertGreaterEqual(manager.started_at, before)
            self.assertEqual(manager.request.battery_id, "physical-battery-1")
            self.assertEqual(len(app.hass.safe_enable_calls), 1)
            self.assertEqual(app.hass.safe_enable_calls[0]["voltage_v"], 14.7)
            self.assertEqual(app.hass.safe_enable_calls[0]["current_a"], 5.0)

            await manager.stop("test_cleanup")
            await manager._retire_runner()


if __name__ == "__main__":
    unittest.main()
