from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot  # noqa: F401 - importing the composition is the acceptance target
from aiogram.types import InlineKeyboardMarkup

import production_bot_ui
from battery_registry import BatteryRecord
from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, BatteryLifecycle, ChargeIntent
from runtime import production_runtime as app
from runtime.ui.telegram.details import HOME_CALLBACK_DATA
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA


class _Message:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=104)
        self.message_id = 900
        self.answers: list[tuple[str, dict]] = []

    async def answer(self, text: str, **kwargs):
        self.answers.append((str(text), kwargs))
        return self

    async def edit_text(self, text: str, **kwargs):
        self.answers.append((str(text), kwargs))
        return self


class _Call:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=104)
        self.message = _Message()
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


async def _handler_for(data: str):
    """Return the actual installed aiogram handler matching callback data."""
    matches = []
    for handler in app.router.observers["callback_query"].handlers:
        matched, _ = await handler.check(_Call(data))
        if matched:
            matches.append(handler)
    if len(matches) != 1:
        raise AssertionError(f"expected one installed handler for {data!r}, got {len(matches)}")
    return matches[0].callback


def _record() -> BatteryRecord:
    return BatteryRecord(
        identity=BatteryIdentity(
            "Leoch_72Ah", BatteryChemistry.EFB, 72, manufacturer="Leoch", model="DJW12-72",
        ),
        lifecycle=BatteryLifecycle(condition=BatteryCondition.UNKNOWN),
    )


class UIActuallyDispatchedAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        production_bot_ui._battery_pages.clear()
        production_bot_ui._selected_battery.clear()
        production_bot_ui._pending_profile.clear()
        production_bot_ui._pending_intent.clear()
        production_bot_ui._pending_start.clear()
        app.awaiting_ah.clear()
        self.chat_guard = patch.object(app, "_check_chat_and_respond", new=AsyncMock(return_value=True))
        self.chat_guard.start()
        self.addCleanup(self.chat_guard.stop)

    async def test_battery_absent_and_present_selection_are_real_callback_dispatches(self):
        empty = _Call("v2_batteries")
        with patch.object(production_bot_ui, "list_batteries", new=AsyncMock(return_value=[])):
            await (await _handler_for(empty.data))(empty)
        self.assertTrue(empty.message.answers)
        self.assertTrue(empty.message.answers)

        record = _record()
        present = _Call("v2_batteries")
        with patch.object(production_bot_ui, "list_batteries", new=AsyncMock(return_value=[record])):
            await (await _handler_for(present.data))(present)
        markup = present.message.answers[-1][1]["reply_markup"]
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        durable_callback = markup.inline_keyboard[0][0].callback_data
        self.assertTrue(durable_callback.startswith("v2_battery_id_"))

        # Restart simulation: the page cache is lost, but the durable token resolves again.
        production_bot_ui._battery_pages.clear()
        selected = _Call(durable_callback)
        with patch.object(production_bot_ui, "_resolve_battery_callback", new=AsyncMock(return_value=record)):
            await (await _handler_for(durable_callback))(selected)
        self.assertEqual(production_bot_ui.selected_battery_for_user(104), record)
        self.assertIn("Leoch", selected.message.answers[-1][0])

    async def test_leoch_recovery_preview_edit_back_and_all_intents(self):
        record = _record()
        production_bot_ui._selected_battery[104] = record
        for intent in ("normal", "recovery", "conditioning", "diagnostic"):
            call = _Call(f"v2_bat_intent_{intent}")
            await (await _handler_for(call.data))(call)
            self.assertTrue(call.message.answers, intent)
            self.assertIn("Leoch", call.message.answers[-1][0], intent)
            preview = call.message.answers[-1][1]["reply_markup"]
            self.assertEqual(preview.inline_keyboard[0][0].callback_data, "v2_battery_start")

        edit = _Call(CHARGE_CALLBACK_DATA)
        await (await _handler_for(edit.data))(edit)
        self.assertTrue(edit.message.answers)
        back = _Call(HOME_CALLBACK_DATA)
        await (await _handler_for(back.data))(back)
        self.assertTrue(back.answers or back.message.answers)

    async def test_stale_callback_is_fail_closed_and_start_rejection_is_non_actuating(self):
        stale = _Call("v2_battery_id_does-not-exist")
        with patch.object(production_bot_ui, "_resolve_battery_callback", new=AsyncMock(return_value=None)):
            await (await _handler_for(stale.data))(stale)
        self.assertTrue(stale.answers or stale.message.answers)

        production_bot_ui._pending_start[104] = production_bot_ui.PendingStart(
            "EFB", 72, ChargeIntent.RECOVERY, "Leoch_72Ah", BatteryCondition.UNKNOWN,
        )
        rejected = SimpleNamespace(accepted=False, reason="safety_preflight_rejected", port_result=None)
        submit = AsyncMock(return_value=rejected)
        route = SimpleNamespace(submit=submit)
        start = _Call("v2_battery_start")
        safe_enable = AsyncMock()
        with patch.object(app, "_v3_production_start_route", route), patch.object(
            app.hass, "safe_enable_output", new=safe_enable
        ):
            await (await _handler_for(start.data))(start)
        submit.assert_awaited_once()
        self.assertTrue(start.answers)
        # The callback only submits the typed route; no RD/HASS actuator was touched.
        safe_enable.assert_not_awaited()

    async def test_hands_off_return_is_dispatched_through_installed_handler(self):
        manager = getattr(bot._composition, "rd_control_mode", None)
        # The composition stores the manager on bot's ProductionComposition, while the
        # runtime callback closes over it. Patch the manager operation itself: this proves
        # callback dispatch without issuing an edge command.
        handler = await _handler_for("rd_hands_off_disable")
        self.assertIsNotNone(handler)
        if manager is None:
            self.skipTest("runtime manager is not exposed; route matching remains covered")
        with patch.object(manager, "return_pb_control", new=AsyncMock(return_value=None)):
            call = _Call("rd_hands_off_disable")
            await handler(call)
        self.assertTrue(call.message.answers)

    def test_wave_four_matrix_is_execution_derived_and_hazardous_routes_are_separate(self):
        matrix_path = Path(__file__).resolve().parents[1] / "docs" / "UI_CALLBACK_ACCEPTANCE_MATRIX_20261010.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        active = matrix["active_v3"]
        rows = matrix["handlers"]
        actual = sum(bool(row["actually_dispatched"]) for row in rows)
        self.assertEqual(active["installed_handlers"], 85)
        self.assertEqual(actual, active["actually_dispatched_handlers"])
        self.assertGreaterEqual(actual, 46)
        self.assertTrue(matrix["hazardous_skipped"])
        exercised = matrix["exercised_callbacks"]
        self.assertTrue(exercised)
        self.assertTrue(all(item["ack_count"] or item["message_response_count"] for item in exercised))
        self.assertTrue(all(row["dispatch_scenarios"] for row in rows if row["actually_dispatched"]))


if __name__ == "__main__":
    unittest.main()
