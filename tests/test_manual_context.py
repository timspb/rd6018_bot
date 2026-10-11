import json
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

import bot  # compose production runtime
from runtime import production_runtime as runtime_app
from manual_context import install_manual_context_ui
from manual_mode import ManualSessionState
from manual_runtime import ProductionManualSessionManager
from manual_text import ManualTextMiddleware


class _CallbackMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=104)
        self.answers = []

    async def answer(self, text="", **kwargs):
        self.answers.append((str(text), kwargs))
        return self


class _Callback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=104)
        self.message = _CallbackMessage()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


async def _installed_callback_handler(data: str):
    matches = []
    probe = _Callback(data)
    for handler in runtime_app.router.observers["callback_query"].handlers:
        matched, _ = await handler.check(probe)
        if matched:
            matches.append(handler)
    if len(matches) != 1:
        raise AssertionError(f"expected one installed handler for {data!r}, got {len(matches)}")
    return matches[0]


class ManualContextEntrypointTests(unittest.TestCase):
    def test_program_menu_routes_manual_through_identity_choice(self) -> None:
        keyboard = runtime_app._build_charge_modes_keyboard()
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("v2_manual_choose", callbacks)
        self.assertEqual(callbacks & {"v2_manual", "v2_manual_choose"}, {"v2_manual_choose"})

    def test_context_callbacks_are_registered(self) -> None:
        handlers = runtime_app.router.observers["callback_query"].handlers
        names = {handler.callback.__name__ for handler in handlers}
        self.assertIn("_manual_choose", names)
        self.assertIn("_manual_bind", names)
        self.assertIn("_manual_interrupted", names)
        self.assertIn("_manual_reauthorize", names)
        self.assertIn("_manual_discard", names)

    def test_old_manual_callback_is_unregistered_and_no_legacy_producer_or_fallback_exists(self) -> None:
        old_matches = []
        current_matches = []
        for handler in runtime_app.router.observers["callback_query"].handlers:
            if asyncio.run(handler.check(_Callback("v2_manual")))[0]:
                old_matches.append(handler)
            if asyncio.run(handler.check(_Callback("v2_manual_choose")))[0]:
                current_matches.append(handler)
        self.assertEqual(old_matches, [])
        self.assertEqual(len(current_matches), 1)
        self.assertEqual(current_matches[0].callback.__name__, "_manual_choose")

        production = Path(__file__).resolve().parents[1]
        sources = [
            path.read_text(encoding="utf-8")
            for path in production.rglob("*.py")
            if "tests" not in path.parts
        ]
        self.assertFalse(any('callback_data="v2_manual"' in source for source in sources))
        self.assertFalse(any("_v2_manual_text_middleware" in source for source in sources))

    def test_single_manual_middleware_owns_bound_and_unbound_inputs(self) -> None:
        manager = runtime_app.router.observers['message'].outer_middleware
        middlewares = [m for m in manager._middlewares if type(m) is ManualTextMiddleware]
        self.assertEqual(len(middlewares), 1)
        self.assertIs(middlewares[0], runtime_app._manual_text_middleware)
        self.assertIsInstance(middlewares[0].pending_battery, dict)
        self.assertIsInstance(middlewares[0].pending_users, set)


class ManualCallbackOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.chat_guard = patch.object(
            runtime_app, "_check_chat_and_respond", new=AsyncMock(return_value=True)
        )
        self.chat_guard.start()
        self.addCleanup(self.chat_guard.stop)
        self.addAsyncCleanup(self._cancel_pending_tasks)

    async def _cancel_pending_tasks(self) -> None:
        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=2)

    async def test_manual_callbacks_are_unique_acknowledged_and_non_actuating(self) -> None:
        import manual_context

        deny_output = AsyncMock(side_effect=AssertionError("manual callback touched output"))
        with patch.object(
            manual_context, "list_batteries", new=AsyncMock(return_value=[])
        ), patch.object(runtime_app.hass, "safe_enable_output", new=deny_output):
            for data in ("v2_manual_choose",):
                handler = await _installed_callback_handler(data)
                call = _Callback(data)
                await asyncio.wait_for(handler.callback(call), timeout=2)
                self.assertTrue(call.answers or call.message.answers, data)
                self.assertEqual(
                    len(
                        [
                            candidate
                            for candidate in runtime_app.router.observers["callback_query"].handlers
                            if (await candidate.check(_Callback(data)))[0]
                        ]
                    ),
                    1,
                    data,
                )
        deny_output.assert_not_awaited()


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
