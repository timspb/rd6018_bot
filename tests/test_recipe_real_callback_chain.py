"""Production callback-chain regression for non-energizing recipe draft creation."""
import asyncio
import tempfile
import types
import unittest
import os
from pathlib import Path

from aiogram import Router
from aiogram.enums import ParseMode

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")
import bot  # Compose the existing production runtime and register its real UI callbacks.

from application.intents import OperatorIntent, OperatorIntentKind
from battery_registry import BatteryRecord
from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    BatteryLifecycle,
    ChargeIntent,
)
from runtime import production_runtime
import production_bot_ui
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from runtime.ui.telegram.charge import legacy_profile_from_callback
from runtime.ui.telegram import battery_selection
from ui_support import profile_for_chemistry


class _App:
    def __init__(self):
        self.router = Router()
        self.ParseMode = ParseMode

    async def _check_chat_and_respond(self, call):
        return True


class _Message:
    def __init__(self):
        self.sent = []

    async def answer(self, text, **kwargs):
        self.sent.append((text, kwargs))
        return types.SimpleNamespace(message_id=100)


class _Call:
    def __init__(self, data, user_id=710061):
        self.data = data
        self.message = _Message()
        self.from_user = types.SimpleNamespace(id=user_id)
        self.acks = []

    async def answer(self, *args, **kwargs):
        self.acks.append((args, kwargs))


class RealRecipeCallbackChainTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _registered_production_callbacks():
        handlers = production_runtime.router.observers["callback_query"].handlers
        callbacks = {handler.callback.__name__: handler.callback for handler in handlers}
        return callbacks

    @staticmethod
    def _recipe_catalog(root):
        return RecipeCatalog(RecipeLibrary(
            Path(root) / "user_recipes", max_voltage_v=15.5, max_current_a=7.2
        ))

    @staticmethod
    def _efb_record():
        return BatteryRecord(
            BatteryIdentity("p6-test-efb", BatteryChemistry.EFB, 60.0),
            BatteryLifecycle(condition=BatteryCondition.UNKNOWN),
        )

    @staticmethod
    def _assert_callbacks_present(test, callbacks):
        test.assertTrue({
            "battery_intent_handler", "pick_recipe_handler",
            "pick_native_recipe_handler", "_battery_start_route",
        }.issubset(callbacks))

    async def test_registered_battery_callback_uses_shared_selection_owner_state(self):
        callbacks = self._registered_production_callbacks()
        self.assertIn("battery_select_handler", callbacks)
        self.assertIs(production_bot_ui._battery_pages, battery_selection._battery_pages)
        self.assertIs(production_bot_ui._selected_battery, battery_selection._selected_battery)
        self.assertIs(production_bot_ui._resolve_battery_callback, battery_selection.resolve_battery_callback)
        self.assertIs(production_bot_ui.selected_battery_for_user, battery_selection.selected_battery_for_user)
        user_id = 710066
        missing = object()
        original_acl = production_runtime._check_chat_and_respond
        original_pages = production_bot_ui._battery_pages.get(user_id, missing)
        original_selected = production_bot_ui._selected_battery.get(user_id, missing)
        original_list = battery_selection.list_batteries
        record = self._efb_record()
        authorized = {"value": True}

        async def chat_acl(_call):
            return authorized["value"]

        async def list_records(*, limit):
            self.assertEqual(limit, 200)
            return [record]

        try:
            production_runtime._check_chat_and_respond = chat_acl
            battery_selection.list_batteries = list_records
            production_bot_ui._battery_pages.pop(user_id, None)
            production_bot_ui._selected_battery.pop(user_id, None)

            callback = production_bot_ui._battery_callback_data(record).replace("v2_battery_", "", 1)
            call = _Call(f"v2_battery_{callback}", user_id)
            await callbacks["battery_select_handler"](call)
            self.assertIs(production_bot_ui.selected_battery_for_user(user_id), record)
            self.assertEqual(len(call.acks), 1)
            self.assertIn("EFB", call.message.sent[0][0])

            repeated = _Call(f"v2_battery_{callback}", user_id)
            await callbacks["battery_select_handler"](repeated)
            self.assertIs(production_bot_ui.selected_battery_for_user(user_id), record)
            self.assertEqual(len(repeated.acks), 1)
            self.assertIn("EFB", repeated.message.sent[0][0])

            unknown = _Call("v2_battery_id_unknown-token", user_id)
            await callbacks["battery_select_handler"](unknown)
            self.assertEqual(len(unknown.message.sent), 1)
            self.assertIn("устарел", unknown.message.sent[0][0])
            self.assertIs(production_bot_ui.selected_battery_for_user(user_id), record)

            authorized["value"] = False
            denied = _Call(f"v2_battery_{callback}", user_id)
            await callbacks["battery_select_handler"](denied)
            self.assertEqual(denied.acks, [])
            self.assertEqual(denied.message.sent, [])
            self.assertIs(production_bot_ui.selected_battery_for_user(user_id), record)

            async def failed_registry_read(*, limit):
                raise OSError(f"registry read failed at limit={limit}")

            authorized["value"] = True
            battery_selection.list_batteries = failed_registry_read
            failed = _Call(f"v2_battery_{callback}", user_id)
            with self.assertRaises(OSError):
                await callbacks["battery_select_handler"](failed)
            self.assertEqual(len(failed.acks), 1)
            self.assertEqual(failed.message.sent, [])
            self.assertIs(production_bot_ui.selected_battery_for_user(user_id), record)
        finally:
            production_runtime._check_chat_and_respond = original_acl
            battery_selection.list_batteries = original_list
            if original_pages is missing:
                production_bot_ui._battery_pages.pop(user_id, None)
            else:
                production_bot_ui._battery_pages[user_id] = original_pages
            if original_selected is missing:
                production_bot_ui._selected_battery.pop(user_id, None)
            else:
                production_bot_ui._selected_battery[user_id] = original_selected

    async def test_registered_legacy_profile_callback_maps_and_keeps_duplicate_click_parity(self):
        callbacks = self._registered_production_callbacks()
        self.assertIn("quick_profile_handler", callbacks)
        self.assertIs(production_bot_ui._profile_from_callback, legacy_profile_from_callback)
        user_id = 710065
        missing = object()
        original_acl = production_runtime._check_chat_and_respond
        original_interface = getattr(production_runtime, "operator_interface", missing)
        original_pending = production_bot_ui._pending_profile.get(user_id, missing)

        async def allow_test_callback(_call):
            return True

        try:
            production_runtime._check_chat_and_respond = allow_test_callback
            production_runtime.operator_interface = None
            production_bot_ui._pending_profile.pop(user_id, None)

            first = _Call("v2_profile_efb", user_id)
            second = _Call("v2_profile_efb", user_id)
            await callbacks["quick_profile_handler"](first)
            await callbacks["quick_profile_handler"](second)

            self.assertEqual(production_bot_ui._pending_profile[user_id], "EFB")
            self.assertEqual(len(first.acks), 1)
            self.assertEqual(len(second.acks), 1)
            self.assertEqual(len(first.message.sent), 1)
            self.assertEqual(len(second.message.sent), 1)
            self.assertIn("EFB", first.message.sent[0][0])

            stale = _Call("v2_profile_unknown", user_id)
            await callbacks["quick_profile_handler"](stale)
            self.assertEqual(stale.acks, [])
            self.assertEqual(stale.message.sent, [])
            self.assertEqual(production_bot_ui._pending_profile[user_id], "EFB")

            async def reject_profile(_intent):
                return types.SimpleNamespace(status="rejected")

            production_runtime.operator_interface = types.SimpleNamespace(
                submit_intent=reject_profile,
            )
            rejected = _Call("v2_profile_agm", user_id)
            await callbacks["quick_profile_handler"](rejected)
            self.assertEqual(len(rejected.acks), 2)
            self.assertEqual(rejected.acks[1][0], ("Профиль недоступен",))
            self.assertTrue(rejected.acks[1][1].get("show_alert"))
            self.assertEqual(rejected.message.sent, [])
            self.assertEqual(production_bot_ui._pending_profile[user_id], "EFB")
        finally:
            production_runtime._check_chat_and_respond = original_acl
            if original_interface is missing:
                delattr(production_runtime, "operator_interface")
            else:
                production_runtime.operator_interface = original_interface
            if original_pending is missing:
                production_bot_ui._pending_profile.pop(user_id, None)
            else:
                production_bot_ui._pending_profile[user_id] = original_pending

    async def test_registered_battery_intent_without_selection_acknowledges_once(self):
        callbacks = self._registered_production_callbacks()
        self._assert_callbacks_present(self, callbacks)
        user_id = 710064
        missing = object()
        original_acl = production_runtime._check_chat_and_respond
        original_pending = production_bot_ui._pending_start.get(user_id, missing)
        original_selected = production_bot_ui._selected_battery.get(user_id, missing)
        submitted = []
        original_route = getattr(production_runtime, "_v3_production_start_route", missing)
        original_route_submit = original_route.submit

        async def allow_test_callback(_call):
            return True

        async def submit(intent):
            submitted.append(intent)

        try:
            production_runtime._check_chat_and_respond = allow_test_callback
            original_route.submit = submit
            production_bot_ui._pending_start.pop(user_id, None)
            production_bot_ui._selected_battery.pop(user_id, None)

            call = _Call("v2_bat_intent_normal", user_id)
            await callbacks["battery_intent_handler"](call)

            self.assertEqual(len(call.acks), 1)
            self.assertEqual(call.acks[0][0], ("Сначала выберите АКБ",))
            self.assertTrue(call.acks[0][1].get("show_alert"))
            self.assertNotIn(user_id, production_bot_ui._pending_start)
            self.assertEqual(call.message.sent, [])
            self.assertEqual(submitted, [])
        finally:
            production_runtime._check_chat_and_respond = original_acl
            if original_route is missing:
                delattr(production_runtime, "_v3_production_start_route")
            else:
                production_runtime._v3_production_start_route = original_route
                original_route.submit = original_route_submit
            if original_pending is missing:
                production_bot_ui._pending_start.pop(user_id, None)
            else:
                production_bot_ui._pending_start[user_id] = original_pending
            if original_selected is missing:
                production_bot_ui._selected_battery.pop(user_id, None)
            else:
                production_bot_ui._selected_battery[user_id] = original_selected

    async def test_registered_start_submit_exception_reports_unconfirmed_and_preserves_pending(self):
        callbacks = self._registered_production_callbacks()
        self._assert_callbacks_present(self, callbacks)
        user_id = 710062
        missing = object()
        original_route = getattr(production_runtime, "_v3_production_start_route", missing)
        original_route_submit = original_route.submit
        original_acl = production_runtime._check_chat_and_respond
        original_pending = production_bot_ui._pending_start.get(user_id, missing)
        original_selected = production_bot_ui._selected_battery.get(user_id, missing)
        original_profile = production_bot_ui._pending_profile.get(user_id, missing)
        original_intent = production_bot_ui._pending_intent.get(user_id, missing)
        original_awaiting = production_runtime.awaiting_ah.get(user_id, missing)
        calls = []

        async def allow_test_callback(_call):
            return True

        async def fail_submit(intent):
            calls.append(("submit", len(call.acks), intent))
            raise RuntimeError("synthetic submit failure")

        try:
            production_runtime._check_chat_and_respond = allow_test_callback
            original_route.submit = fail_submit
            production_bot_ui._selected_battery[user_id] = self._efb_record()
            production_bot_ui._pending_profile[user_id] = "EFB"
            production_bot_ui._pending_intent[user_id] = ChargeIntent.NORMAL
            production_runtime.awaiting_ah[user_id] = "EFB"
            pending = production_bot_ui.PendingStart(
                profile=profile_for_chemistry(BatteryChemistry.EFB),
                capacity_ah=60.0,
                intent=ChargeIntent.NORMAL,
                battery_id="p6-test-efb",
                condition=BatteryCondition.UNKNOWN,
            )
            production_bot_ui._pending_start[user_id] = pending

            call = _Call("v2_battery_start", user_id)
            await callbacks["_battery_start_route"](call)

            self.assertEqual(len(call.acks), 1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "submit")
            self.assertEqual(calls[0][1], 1)
            self.assertIsInstance(calls[0][2], OperatorIntent)
            self.assertEqual(calls[0][2].parameters["profile"], profile_for_chemistry(BatteryChemistry.EFB))
            self.assertEqual(calls[0][2].parameters["capacity_ah"], 60.0)
            self.assertEqual(calls[0][2].parameters["battery_id"], "p6-test-efb")
            self.assertEqual(len(call.message.sent), 1)
            feedback = call.message.sent[0][0].lower()
            self.assertIn("не удалось подтвердить", feedback)
            self.assertIn("повтор", feedback)
            self.assertNotIn("включ", feedback)
            self.assertNotIn("выключ", feedback)
            self.assertEqual(production_bot_ui._pending_start[user_id], pending)
            self.assertEqual(production_bot_ui._pending_profile[user_id], "EFB")
            self.assertEqual(production_bot_ui._pending_intent[user_id], ChargeIntent.NORMAL)
            self.assertEqual(production_runtime.awaiting_ah[user_id], "EFB")
            self.assertEqual(production_bot_ui._selected_battery[user_id].identity.battery_id, "p6-test-efb")
            self.assertEqual(len(call.acks), 1)
        finally:
            production_runtime._check_chat_and_respond = original_acl
            if original_route is missing:
                delattr(production_runtime, "_v3_production_start_route")
            else:
                production_runtime._v3_production_start_route = original_route
                original_route.submit = original_route_submit
            if original_pending is missing:
                production_bot_ui._pending_start.pop(user_id, None)
            else:
                production_bot_ui._pending_start[user_id] = original_pending
            if original_selected is missing:
                production_bot_ui._selected_battery.pop(user_id, None)
            else:
                production_bot_ui._selected_battery[user_id] = original_selected
            for mapping, original in (
                (production_bot_ui._pending_profile, original_profile),
                (production_bot_ui._pending_intent, original_intent),
                (production_runtime.awaiting_ah, original_awaiting),
            ):
                if original is missing:
                    mapping.pop(user_id, None)
                else:
                    mapping[user_id] = original

    async def test_registered_start_cancellation_propagates_without_claim_or_retry(self):
        callbacks = self._registered_production_callbacks()
        user_id = 710067
        missing = object()
        original_route = getattr(production_runtime, "_v3_production_start_route", missing)
        original_route_submit = original_route.submit
        original_acl = production_runtime._check_chat_and_respond
        original_pending = production_bot_ui._pending_start.get(user_id, missing)
        submissions = []

        async def allow_test_callback(_call):
            return True

        async def cancel_submit(_intent):
            submissions.append("submit")
            raise asyncio.CancelledError()

        try:
            production_runtime._check_chat_and_respond = allow_test_callback
            original_route.submit = cancel_submit
            pending = production_bot_ui.PendingStart(
                profile="EFB", capacity_ah=60.0, intent=ChargeIntent.NORMAL,
                battery_id="p6-test-efb", condition=BatteryCondition.UNKNOWN,
            )
            production_bot_ui._pending_start[user_id] = pending
            call = _Call("v2_battery_start", user_id)
            with self.assertRaises(asyncio.CancelledError):
                await callbacks["_battery_start_route"](call)
            self.assertEqual(submissions, ["submit"])
            self.assertEqual(len(call.acks), 1)
            self.assertEqual(call.message.sent, [])
            self.assertIs(production_bot_ui._pending_start[user_id], pending)
        finally:
            production_runtime._check_chat_and_respond = original_acl
            if original_route is missing:
                delattr(production_runtime, "_v3_production_start_route")
            else:
                production_runtime._v3_production_start_route = original_route
                original_route.submit = original_route_submit
            if original_pending is missing:
                production_bot_ui._pending_start.pop(user_id, None)
            else:
                production_bot_ui._pending_start[user_id] = original_pending

    async def test_registered_start_response_delivery_exception_is_swallowed(self):
        callbacks = self._registered_production_callbacks()
        self._assert_callbacks_present(self, callbacks)
        user_id = 710063
        missing = object()
        original_route = getattr(production_runtime, "_v3_production_start_route", missing)
        original_route_submit = original_route.submit
        original_acl = production_runtime._check_chat_and_respond
        original_pending = production_bot_ui._pending_start.get(user_id, missing)
        original_selected = production_bot_ui._selected_battery.get(user_id, missing)
        events = []

        async def allow_test_callback(_call):
            return True

        async def accept_submit(intent):
            events.append(("submit", len(call.acks), intent))
            return types.SimpleNamespace(accepted=True, reason="", trace_id="fake", port_result=None)

        async def fail_delivery(text, **_kwargs):
            events.append(("delivery", text))
            raise RuntimeError("synthetic Telegram delivery failure")

        try:
            production_runtime._check_chat_and_respond = allow_test_callback
            original_route.submit = accept_submit
            production_bot_ui._selected_battery[user_id] = self._efb_record()
            pending = production_bot_ui.PendingStart(
                profile=profile_for_chemistry(BatteryChemistry.EFB),
                capacity_ah=60.0,
                intent=ChargeIntent.NORMAL,
                battery_id="p6-test-efb",
                condition=BatteryCondition.UNKNOWN,
            )
            production_bot_ui._pending_start[user_id] = pending
            call = _Call("v2_battery_start", user_id)
            call.message.answer = fail_delivery

            await callbacks["_battery_start_route"](call)

            self.assertEqual(len(call.acks), 1)
            self.assertEqual([event[0] for event in events], ["submit", "delivery"])
            self.assertEqual(events[0][1], 1)
            self.assertIsInstance(events[0][2], OperatorIntent)
            self.assertIn("START", events[1][1])
            self.assertEqual(production_bot_ui._pending_start[user_id], pending)
            self.assertEqual(len(events), 2)
            self.assertEqual(len(call.acks), 1)
        finally:
            production_runtime._check_chat_and_respond = original_acl
            if original_route is missing:
                delattr(production_runtime, "_v3_production_start_route")
            else:
                production_runtime._v3_production_start_route = original_route
                original_route.submit = original_route_submit
            if original_pending is missing:
                production_bot_ui._pending_start.pop(user_id, None)
            else:
                production_bot_ui._pending_start[user_id] = original_pending
            if original_selected is missing:
                production_bot_ui._selected_battery.pop(user_id, None)
            else:
                production_bot_ui._selected_battery[user_id] = original_selected

    async def test_registered_quick_profile_ah_intent_start_uses_same_pending_owner(self):
        callbacks = self._registered_production_callbacks()
        user_id = 710060
        missing = object()
        maps = (
            production_bot_ui._pending_profile,
            production_bot_ui._pending_intent,
            production_bot_ui._pending_start,
            production_runtime.awaiting_ah,
        )
        originals = [mapping.get(user_id, missing) for mapping in maps]
        original_acl = production_runtime._check_chat_and_respond
        original_interface = getattr(production_runtime, "operator_interface", missing)
        original_route = getattr(production_runtime, "_v3_production_start_route", missing)
        original_route_submit = original_route.submit
        results = [
            types.SimpleNamespace(accepted=False, reason="rejected", trace_id="fake",
                                  port_result=None),
            types.SimpleNamespace(accepted=True, reason="accepted", trace_id="fake",
                                  port_result=None),
        ]
        submitted = []

        async def allow(_event):
            return True

        async def submit(intent):
            submitted.append(intent)
            return results.pop(0)

        try:
            production_runtime._check_chat_and_respond = allow
            production_runtime.operator_interface = None
            original_route.submit = submit

            async def replaced_route_submit(_intent):
                raise AssertionError("callback resolved a replaced app route")

            production_runtime._v3_production_start_route = types.SimpleNamespace(
                submit=replaced_route_submit
            )
            for mapping in maps:
                mapping.pop(user_id, None)

            profile = _Call("v2_profile_agm", user_id)
            await callbacks["quick_profile_handler"](profile)
            self.assertEqual(production_bot_ui._pending_profile[user_id], "AGM")
            self.assertEqual(
                production_bot_ui.selected_program_for_user(user_id),
                "AGM · ожидается ёмкость АКБ",
            )

            intent = _Call("v2_quick_intent_recovery", user_id)
            await callbacks["quick_intent_handler"](intent)
            self.assertEqual(production_bot_ui._pending_intent[user_id], ChargeIntent.RECOVERY)
            self.assertEqual(production_runtime.awaiting_ah[user_id], "AGM")

            message = _Message()
            message.text = "90"
            message.from_user = types.SimpleNamespace(id=user_id)
            await production_runtime.handle_ah_input(message, "AGM", user_id)
            pending = production_bot_ui._pending_start[user_id]
            self.assertEqual((pending.profile, pending.capacity_ah, pending.intent),
                             ("AGM", 90.0, ChargeIntent.RECOVERY))
            self.assertEqual(
                production_bot_ui.selected_program_for_user(user_id),
                "AGM 90 Ah · Восстановление",
            )

            rejected = _Call("v2_quick_start", user_id)
            await callbacks["quick_start_handler"](rejected)
            self.assertIs(production_bot_ui._pending_start[user_id], pending)
            self.assertEqual(production_bot_ui._pending_profile[user_id], "AGM")
            # AH input consumed the intent and awaiting-Ah marker before START;
            # rejecting START preserves the already materialized PendingStart.
            self.assertNotIn(user_id, production_bot_ui._pending_intent)
            self.assertNotIn(user_id, production_runtime.awaiting_ah)

            accepted = _Call("v2_quick_start", user_id)
            await callbacks["quick_start_handler"](accepted)
            self.assertEqual(len(submitted), 2)
            self.assertEqual(submitted[-1].parameters["intent"], ChargeIntent.RECOVERY)
            self.assertNotIn(user_id, production_bot_ui._pending_profile)
            self.assertNotIn(user_id, production_bot_ui._pending_intent)
            self.assertNotIn(user_id, production_bot_ui._pending_start)
            self.assertNotIn(user_id, production_runtime.awaiting_ah)
        finally:
            production_runtime._check_chat_and_respond = original_acl
            if original_interface is missing:
                delattr(production_runtime, "operator_interface")
            else:
                production_runtime.operator_interface = original_interface
            if original_route is missing:
                delattr(production_runtime, "_v3_production_start_route")
            else:
                production_runtime._v3_production_start_route = original_route
                original_route.submit = original_route_submit
            for mapping, original in zip(maps, originals):
                if original is missing:
                    mapping.pop(user_id, None)
                else:
                    mapping[user_id] = original

    async def test_registered_step_recipe_pick_reaches_fake_start_route(self):
        callbacks = self._registered_production_callbacks()
        self._assert_callbacks_present(self, callbacks)
        user_id = 710061
        missing = object()
        original_route = getattr(production_runtime, "_v3_production_start_route", missing)
        original_route_submit = original_route.submit
        original_catalog = getattr(production_runtime, "_user_recipe_catalog", missing)
        original_acl = production_runtime._check_chat_and_respond
        original_pending = production_bot_ui._pending_start.get(user_id, missing)
        original_selected = production_bot_ui._selected_battery.get(user_id, missing)
        original_profile = production_bot_ui._pending_profile.get(user_id, missing)
        original_intent = production_bot_ui._pending_intent.get(user_id, missing)
        original_awaiting = production_runtime.awaiting_ah.get(user_id, missing)
        other_user_id = user_id + 100
        original_other_profile = production_bot_ui._pending_profile.get(other_user_id, missing)
        original_other_intent = production_bot_ui._pending_intent.get(other_user_id, missing)
        original_other_pending = production_bot_ui._pending_start.get(other_user_id, missing)
        original_other_awaiting = production_runtime.awaiting_ah.get(other_user_id, missing)
        submitted = []
        accepted = {"value": False}

        async def allow_test_callback(_call):
            return True

        async def record_submit(intent):
            submitted.append(intent)
            return types.SimpleNamespace(
                accepted=accepted["value"], reason="synthetic rejection", trace_id="fake",
                port_result=None,
            )

        try:
            production_runtime._check_chat_and_respond = allow_test_callback
            original_route.submit = record_submit
            with tempfile.TemporaryDirectory() as root:
                catalog = self._recipe_catalog(root)
                catalog.library.save({
                    "id": "p6_step", "version": 1,
                    "steps": [{"action": "off", "params": {},
                               "until": {"after_seconds": 1}}],
                })
                production_runtime._user_recipe_catalog = catalog
                production_bot_ui._selected_battery[user_id] = self._efb_record()
                production_bot_ui._pending_profile[user_id] = "EFB"
                production_bot_ui._pending_intent[user_id] = ChargeIntent.NORMAL
                production_runtime.awaiting_ah[user_id] = "EFB"
                production_bot_ui._pending_start.pop(user_id, None)

                other_user_pending = production_bot_ui.PendingStart(
                    "AGM", 90.0, ChargeIntent.RECOVERY, "other-user",
                    BatteryCondition.UNKNOWN,
                )
                production_bot_ui._pending_profile[other_user_id] = "AGM"
                production_bot_ui._pending_intent[other_user_id] = ChargeIntent.RECOVERY
                production_bot_ui._pending_start[other_user_id] = other_user_pending
                production_runtime.awaiting_ah[other_user_id] = "AGM"

                intent_call = _Call("v2_bat_intent_normal", user_id)
                await callbacks["battery_intent_handler"](intent_call)
                self.assertEqual(len(intent_call.acks), 1)
                pending = production_bot_ui._pending_start[user_id]
                self.assertEqual(pending.profile, profile_for_chemistry(BatteryChemistry.EFB))
                self.assertEqual(pending.capacity_ah, 60.0)
                self.assertEqual(pending.intent, ChargeIntent.NORMAL)
                self.assertEqual(pending.battery_id, "p6-test-efb")
                self.assertEqual(pending.condition, BatteryCondition.UNKNOWN)
                self.assertIsNone(pending.recipe_id)
                self.assertIsNone(pending.recipe_version)
                self.assertIsNone(pending.native_recipe_name)
                self.assertIsNone(pending.native_recipe_version)
                preview_data = [button.callback_data
                                for row in intent_call.message.sent[0][1]["reply_markup"].inline_keyboard
                                for button in row]
                self.assertIn("v2_recipe_pick:p6_step:1", preview_data)
                self.assertIn("v2_battery_start", preview_data)

                pick_call = _Call("v2_recipe_pick:p6_step:1", user_id)
                await callbacks["pick_recipe_handler"](pick_call)
                self.assertEqual(len(pick_call.acks), 1)
                pending = production_bot_ui._pending_start[user_id]
                self.assertEqual((pending.recipe_id, pending.recipe_version), ("p6_step", 1))
                self.assertIsNone(pending.native_recipe_name)
                self.assertIsNone(pending.native_recipe_version)
                pick_data = [button.callback_data
                             for row in pick_call.message.sent[0][1]["reply_markup"].inline_keyboard
                             for button in row]
                self.assertIn("v2_battery_start", pick_data)

                rejected_call = _Call("v2_battery_start", user_id)
                await callbacks["_battery_start_route"](rejected_call)
                self.assertEqual(production_bot_ui._pending_start[user_id], pending)
                self.assertEqual(production_bot_ui._pending_profile[user_id], "EFB")
                self.assertEqual(production_bot_ui._pending_intent[user_id], ChargeIntent.NORMAL)
                self.assertEqual(production_runtime.awaiting_ah[user_id], "EFB")
                self.assertIn("отклонён", rejected_call.message.sent[0][0])
                submitted.clear()

                accepted["value"] = True
                start_call = _Call("v2_battery_start", user_id)
                await callbacks["_battery_start_route"](start_call)
                self.assertEqual(len(start_call.acks), 1)
                self.assertEqual(len(start_call.message.sent), 1)
                self.assertEqual(submitted, [OperatorIntent(
                    OperatorIntentKind.START_CHARGE, "telegram", str(user_id), {
                        "profile": profile_for_chemistry(BatteryChemistry.EFB),
                        "capacity_ah": 60.0,
                        "battery_identity": None,
                        "battery_id": "p6-test-efb",
                        "intent": ChargeIntent.NORMAL,
                        "condition": BatteryCondition.UNKNOWN,
                        "user_recipe_id": "p6_step",
                        "user_recipe_version": 1,
                        "native_recipe_name": None,
                        "native_recipe_version": None,
                    },
                )])
                self.assertNotIn(user_id, production_bot_ui._pending_profile)
                self.assertNotIn(user_id, production_bot_ui._pending_intent)
                self.assertNotIn(user_id, production_bot_ui._pending_start)
                self.assertNotIn(user_id, production_runtime.awaiting_ah)
                self.assertIsNotNone(production_bot_ui.selected_battery_for_user(user_id))
                self.assertEqual(production_bot_ui._pending_profile[other_user_id], "AGM")
                self.assertEqual(production_bot_ui._pending_intent[other_user_id], ChargeIntent.RECOVERY)
                self.assertIs(production_bot_ui._pending_start[other_user_id], other_user_pending)
                self.assertEqual(production_runtime.awaiting_ah[other_user_id], "AGM")
        finally:
            for mapping, key, original in (
                (production_bot_ui._pending_profile, user_id, original_profile),
                (production_bot_ui._pending_intent, user_id, original_intent),
                (production_runtime.awaiting_ah, user_id, original_awaiting),
                (production_bot_ui._pending_profile, other_user_id, original_other_profile),
                (production_bot_ui._pending_intent, other_user_id, original_other_intent),
                (production_bot_ui._pending_start, other_user_id, original_other_pending),
                (production_runtime.awaiting_ah, other_user_id, original_other_awaiting),
            ):
                if original is missing:
                    mapping.pop(key, None)
                else:
                    mapping[key] = original
            production_runtime._check_chat_and_respond = original_acl
            if original_route is missing:
                delattr(production_runtime, "_v3_production_start_route")
            else:
                production_runtime._v3_production_start_route = original_route
                original_route.submit = original_route_submit
            if original_catalog is missing:
                delattr(production_runtime, "_user_recipe_catalog")
            else:
                production_runtime._user_recipe_catalog = original_catalog
            if original_pending is missing:
                production_bot_ui._pending_start.pop(user_id, None)
            else:
                production_bot_ui._pending_start[user_id] = original_pending
            if original_selected is missing:
                production_bot_ui._selected_battery.pop(user_id, None)
            else:
                production_bot_ui._selected_battery[user_id] = original_selected

    async def test_registered_native_draft_pick_reaches_fake_start_route(self):
        callbacks = self._registered_production_callbacks()
        self._assert_callbacks_present(self, callbacks)
        user_id = 710061
        missing = object()
        original_route = getattr(production_runtime, "_v3_production_start_route", missing)
        original_route_submit = original_route.submit
        original_catalog = getattr(production_runtime, "_user_recipe_catalog", missing)
        original_acl = production_runtime._check_chat_and_respond
        original_pending = production_bot_ui._pending_start.get(user_id, missing)
        original_selected = production_bot_ui._selected_battery.get(user_id, missing)
        submitted = []

        async def allow_test_callback(_call):
            return True

        async def record_submit(intent):
            submitted.append(intent)
            # Match the typed START route result consumed by the production
            # callback. This fake ends before execution and has no port receipt.
            return types.SimpleNamespace(
                accepted=True, reason="", trace_id="fake", port_result=None
            )

        try:
            production_runtime._check_chat_and_respond = allow_test_callback
            original_route.submit = record_submit
            with tempfile.TemporaryDirectory() as root:
                catalog = self._recipe_catalog(root)
                NativeRecipeDraftLibrary(Path(root) / "native_recipe_drafts").save(
                    "my_efb", 1, {
                        "schema": 1, "base_recipe_id": "native_efb_normal",
                        "execution_kind": "native_authority", "overrides": {},
                    },
                )
                production_runtime._user_recipe_catalog = catalog
                production_bot_ui._selected_battery[user_id] = self._efb_record()
                production_bot_ui._pending_start.pop(user_id, None)

                intent_call = _Call("v2_bat_intent_normal", user_id)
                await callbacks["battery_intent_handler"](intent_call)
                self.assertEqual(len(intent_call.acks), 1)
                self.assertIsNone(production_bot_ui._pending_start[user_id].native_recipe_name)
                preview_data = [button.callback_data
                                for row in intent_call.message.sent[0][1]["reply_markup"].inline_keyboard
                                for button in row]
                self.assertIn("v2_native_pick:my_efb:1", preview_data)
                self.assertIn("v2_battery_start", preview_data)

                pick_call = _Call("v2_native_pick:my_efb:1", user_id)
                await callbacks["pick_native_recipe_handler"](pick_call)
                self.assertEqual(len(pick_call.acks), 1)
                pending = production_bot_ui._pending_start[user_id]
                self.assertEqual((pending.native_recipe_name, pending.native_recipe_version),
                                 ("my_efb", 1))
                self.assertIsNone(pending.recipe_id)
                self.assertIsNone(pending.recipe_version)
                pick_data = [button.callback_data
                             for row in pick_call.message.sent[0][1]["reply_markup"].inline_keyboard
                             for button in row]
                self.assertIn("v2_battery_start", pick_data)

                start_call = _Call("v2_battery_start", user_id)
                await callbacks["_battery_start_route"](start_call)
                self.assertEqual(len(start_call.acks), 1)
                self.assertEqual(len(start_call.message.sent), 1)
                self.assertEqual(submitted, [OperatorIntent(
                    OperatorIntentKind.START_CHARGE, "telegram", str(user_id), {
                        "profile": profile_for_chemistry(BatteryChemistry.EFB),
                        "capacity_ah": 60.0,
                        "battery_identity": None,
                        "battery_id": "p6-test-efb",
                        "intent": ChargeIntent.NORMAL,
                        "condition": BatteryCondition.UNKNOWN,
                        "user_recipe_id": None,
                        "user_recipe_version": None,
                        "native_recipe_name": "my_efb",
                        "native_recipe_version": 1,
                    },
                )])
                self.assertNotIn(user_id, production_bot_ui._pending_start)
                self.assertIsNotNone(production_bot_ui.selected_battery_for_user(user_id))
        finally:
            production_runtime._check_chat_and_respond = original_acl
            if original_route is missing:
                delattr(production_runtime, "_v3_production_start_route")
            else:
                production_runtime._v3_production_start_route = original_route
                original_route.submit = original_route_submit
            if original_catalog is missing:
                delattr(production_runtime, "_user_recipe_catalog")
            else:
                production_runtime._user_recipe_catalog = original_catalog
            if original_pending is missing:
                production_bot_ui._pending_start.pop(user_id, None)
            else:
                production_bot_ui._pending_start[user_id] = original_pending
            if original_selected is missing:
                production_bot_ui._selected_battery.pop(user_id, None)
            else:
                production_bot_ui._selected_battery[user_id] = original_selected

    async def test_registered_recipe_selection_rejections_never_submit_start(self):
        callbacks = self._registered_production_callbacks()
        self._assert_callbacks_present(self, callbacks)
        user_id = 710061
        missing = object()
        original_route = getattr(production_runtime, "_v3_production_start_route", missing)
        original_route_submit = original_route.submit
        original_catalog = getattr(production_runtime, "_user_recipe_catalog", missing)
        original_acl = production_runtime._check_chat_and_respond
        original_pending = production_bot_ui._pending_start.get(user_id, missing)
        original_selected = production_bot_ui._selected_battery.get(user_id, missing)
        submitted = []

        async def allow_test_callback(_call):
            return True

        async def record_submit(intent):
            submitted.append(intent)
            return types.SimpleNamespace(accepted=True, reason="", trace_id="fake", port_result=None)

        try:
            production_runtime._check_chat_and_respond = allow_test_callback
            original_route.submit = record_submit
            with tempfile.TemporaryDirectory() as root:
                production_bot_ui._selected_battery[user_id] = self._efb_record()
                production_bot_ui._pending_start.pop(user_id, None)

                # An archived step recipe and a nonexistent immutable version
                # both remain unpinned and cannot reach the START submit sink.
                catalog = self._recipe_catalog(Path(root) / "archived")
                catalog.library.save({
                    "id": "archived_step", "version": 1,
                    "steps": [{"action": "off", "params": {},
                               "until": {"after_seconds": 1}}],
                })
                catalog.archive("archived_step")
                production_runtime._user_recipe_catalog = catalog
                intent_call = _Call("v2_bat_intent_normal", user_id)
                await callbacks["battery_intent_handler"](intent_call)
                initial = production_bot_ui._pending_start[user_id]
                pick_call = _Call("v2_recipe_pick:archived_step:1", user_id)
                await callbacks["pick_recipe_handler"](pick_call)
                self.assertEqual(len(pick_call.acks), 1)
                self.assertTrue(pick_call.acks[0][1].get("show_alert"))
                self.assertEqual(production_bot_ui._pending_start[user_id], initial)
                self.assertFalse(pick_call.message.sent)
                self.assertEqual(submitted, [])

                production_bot_ui._pending_start.pop(user_id, None)
                production_bot_ui._selected_battery[user_id] = self._efb_record()
                catalog = self._recipe_catalog(Path(root) / "missing_step_version")
                catalog.library.save({
                    "id": "versioned_step", "version": 1,
                    "steps": [{"action": "off", "params": {},
                               "until": {"after_seconds": 1}}],
                })
                production_runtime._user_recipe_catalog = catalog
                intent_call = _Call("v2_bat_intent_normal", user_id)
                await callbacks["battery_intent_handler"](intent_call)
                initial = production_bot_ui._pending_start[user_id]
                pick_call = _Call("v2_recipe_pick:versioned_step:99", user_id)
                await callbacks["pick_recipe_handler"](pick_call)
                self.assertEqual(len(pick_call.acks), 1)
                self.assertTrue(pick_call.acks[0][1].get("show_alert"))
                self.assertEqual(production_bot_ui._pending_start[user_id], initial)
                self.assertFalse(pick_call.message.sent)
                self.assertEqual(submitted, [])

                # A valid native draft with a different intent and one with a
                # different profile must both be rejected at callback selection.
                for index, base_recipe_id in enumerate((
                    "native_efb_recovery", "native_agm_normal",
                ), start=1):
                    production_bot_ui._pending_start.pop(user_id, None)
                    production_bot_ui._selected_battery[user_id] = self._efb_record()
                    catalog = self._recipe_catalog(Path(root) / f"native_wrong_{index}")
                    NativeRecipeDraftLibrary(Path(root) / f"native_wrong_{index}" / "native_recipe_drafts").save(
                        "wrong_copy", 1, {
                            "schema": 1, "base_recipe_id": base_recipe_id,
                            "execution_kind": "native_authority", "overrides": {},
                        },
                    )
                    production_runtime._user_recipe_catalog = catalog
                    intent_call = _Call("v2_bat_intent_normal", user_id)
                    await callbacks["battery_intent_handler"](intent_call)
                    initial = production_bot_ui._pending_start[user_id]
                    pick_call = _Call("v2_native_pick:wrong_copy:1", user_id)
                    await callbacks["pick_native_recipe_handler"](pick_call)
                    self.assertEqual(len(pick_call.acks), 1)
                    self.assertTrue(pick_call.acks[0][1].get("show_alert"))
                    self.assertEqual(production_bot_ui._pending_start[user_id], initial)
                    self.assertFalse(pick_call.message.sent)
                    self.assertEqual(submitted, [])

                # Existing draft name, absent requested version.
                production_bot_ui._pending_start.pop(user_id, None)
                production_bot_ui._selected_battery[user_id] = self._efb_record()
                catalog = self._recipe_catalog(Path(root) / "native_missing_version")
                NativeRecipeDraftLibrary(
                    Path(root) / "native_missing_version" / "native_recipe_drafts"
                ).save("missing_version", 1, {
                    "schema": 1, "base_recipe_id": "native_efb_normal",
                    "execution_kind": "native_authority", "overrides": {},
                })
                production_runtime._user_recipe_catalog = catalog
                intent_call = _Call("v2_bat_intent_normal", user_id)
                await callbacks["battery_intent_handler"](intent_call)
                initial = production_bot_ui._pending_start[user_id]
                pick_call = _Call("v2_native_pick:missing_version:2", user_id)
                await callbacks["pick_native_recipe_handler"](pick_call)
                self.assertEqual(len(pick_call.acks), 1)
                self.assertTrue(pick_call.acks[0][1].get("show_alert"))
                self.assertEqual(production_bot_ui._pending_start[user_id], initial)
                self.assertFalse(pick_call.message.sent)
                self.assertEqual(submitted, [])
        finally:
            production_runtime._check_chat_and_respond = original_acl
            if original_route is missing:
                delattr(production_runtime, "_v3_production_start_route")
            else:
                production_runtime._v3_production_start_route = original_route
                original_route.submit = original_route_submit
            if original_catalog is missing:
                delattr(production_runtime, "_user_recipe_catalog")
            else:
                production_runtime._user_recipe_catalog = original_catalog
            if original_pending is missing:
                production_bot_ui._pending_start.pop(user_id, None)
            else:
                production_bot_ui._pending_start[user_id] = original_pending
            if original_selected is missing:
                production_bot_ui._selected_battery.pop(user_id, None)
            else:
                production_bot_ui._selected_battery[user_id] = original_selected

    async def test_create_draft_to_editor_without_hardware_or_start(self):
        with tempfile.TemporaryDirectory() as path:
            catalog = RecipeCatalog(RecipeLibrary(
                path, max_voltage_v=15.5, max_current_a=7.2
            ))
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = {h.callback.__name__: h.callback
                        for h in app.router.callback_query.handlers}

            create = _Call("recipes:create")
            await handlers["create_draft"](create)
            self.assertEqual(len(create.acks), 1)
            self.assertEqual(len(create.message.sent), 1)
            (name,) = catalog.list_recipes()
            recipe = catalog.library.load(name, 1)
            self.assertTrue(name.startswith("draft_"))
            self.assertEqual(recipe.steps[0]["action"], "off")

            buttons = create.message.sent[0][1]["reply_markup"].inline_keyboard
            data = [button.callback_data for row in buttons for button in row]
            self.assertIn(f"recipes:edit:{name}:1", data)

            edit = _Call(f"recipes:edit:{name}:1")
            await handlers["edit_menu"](edit)
            self.assertEqual(len(edit.message.sent), 1)
            buttons = edit.message.sent[0][1]["reply_markup"].inline_keyboard
            data = [button.callback_data for row in buttons for button in row]
            self.assertIn(f"recipes:append:{name}:1:set", data)
            self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in data))
            self.assertEqual(catalog.library.versions(name), (1,))

    async def test_user_recipe_browser_list_callback_keeps_acl_and_registration(self):
        from runtime.ui.telegram import recipe_buttons, recipe_menu_view

        for name in ("catalog_markup", "recipe_markup", "recipe_history_markup"):
            self.assertIs(getattr(recipe_buttons, name), getattr(recipe_menu_view, name))
        with tempfile.TemporaryDirectory() as path:
            catalog = RecipeCatalog(RecipeLibrary(
                path, max_voltage_v=15.5, max_current_a=7.2
            ))
            catalog.library.save({
                "id": "browser_item", "version": 1,
                "steps": [{"action": "off", "params": {},
                           "until": {"after_seconds": 1}}],
            })
            app = _App()
            install_recipe_catalog_commands(app, catalog=catalog)
            handlers = [h.callback for h in app.router.callback_query.handlers]
            names = [handler.__name__ for handler in handlers]
            expected = [
                "native_catalog", "native_recipe_details", "native_recipe_parameters_view",
                "check_recipe", "create_draft", "show_list", "show_recipe",
                "recipe_history", "recipe_duplicate", "recipe_archive_ask",
                "recipe_archive_confirm", "copy_help", "edit_menu",
            ]
            start = names.index(expected[0])
            self.assertEqual(names[start:start + len(expected)], expected)

            callback = {handler.__name__: handler for handler in handlers}["show_list"]
            call = _Call("recipes:list:0")
            await callback(call)
            self.assertEqual(len(call.acks), 1)
            self.assertIn("recipes:view:browser_item:1", [
                button.callback_data
                for row in call.message.sent[0][1]["reply_markup"].inline_keyboard
                for button in row
            ])

            async def denied(_call):
                return False

            async def forbidden_lookup():
                raise AssertionError("catalog lookup ran before ACL")

            app._check_chat_and_respond = denied
            catalog.list_recipes = forbidden_lookup
            rejected = _Call("recipes:list:0")
            await callback(rejected)
            self.assertEqual(rejected.acks, [])
            self.assertEqual(rejected.message.sent, [])
