import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA
from runtime.ui.telegram.off_conditions import OFF_CALLBACK_DATA
from telegram_panel import (
    PanelLastMiddleware,
    TerminalPanelManager,
    _TERMINAL_CALLBACKS,
    _is_workspace_callback,
    install_panel_last,
)


class FakeBot:
    def __init__(self):
        self.deleted = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))
        return True


class FakeObserver:
    def __init__(self):
        self.middleware = []

    def outer_middleware(self, middleware):
        self.middleware.append(middleware)


class FakeRouter:
    def __init__(self):
        self.message = FakeObserver()
        self.callback_query = FakeObserver()


class FakeApp:
    def __init__(self):
        self.bot = FakeBot()
        self.router = FakeRouter()
        self.user_dashboard = {}
        self.chat_dashboard = {}
        self.last_chat_id = 10
        self.last_user_id = 20
        self.next_panel = 100
        self.render_calls = []
        self.refresh_calls = []
        self.notifications = []
        self.scheduled = []

    async def _build_and_send_dashboard(
        self,
        chat_id,
        user_id,
        old_msg_id=None,
        anchor_msg_id=None,
    ):
        self.render_calls.append((chat_id, user_id, old_msg_id, anchor_msg_id))
        self.next_panel += 1
        panel_id = self.next_panel
        self.user_dashboard[user_id] = panel_id
        self.chat_dashboard[chat_id] = panel_id
        return panel_id

    async def _refresh_operator_panel(self, chat_id, user_id, message_id):
        self.refresh_calls.append((chat_id, user_id, message_id))
        return message_id

    def schedule_dashboard_after_60(self, chat_id, user_id=0):
        self.scheduled.append((chat_id, user_id))

    async def _send_notify_safe(self, msg, critical=True):
        self.notifications.append((msg, critical))


class FakeEventManager:
    def __init__(self):
        self.events = []

    async def after_event(self, event):
        self.events.append(event)


class TerminalPanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_graph_adopts_only_after_send_then_starts_existing_refresh(self):
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        order = []

        async def send():
            order.append("send")
            return SimpleNamespace(message_id=88)

        def after_publish():
            order.append("cache")

        refresh = object()
        result = await manager.publish_graph_workspace(10, 20, send, after_publish, refresh)

        self.assertEqual(result, 88)
        self.assertEqual(order, ["send", "cache"])
        self.assertEqual(manager.graph_id(10, 20), 88)
        self.assertEqual(manager.panel_id(10), 88)
        self.assertIs(manager._graph_refresh_callback, refresh)
        self.assertIsNotNone(manager._graph_refresh_task)
        manager._graph_refresh_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await manager._graph_refresh_task

    async def test_ensure_last_graph_publication_uses_existing_chat_lock_without_deadlock(self):
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        events = []

        async def nested_dashboard(**kwargs):
            async def send():
                events.append("send")
                return SimpleNamespace(message_id=111)

            return await manager.publish_graph_workspace(
                kwargs["chat_id"], kwargs["user_id"], send,
                lambda: events.append("cache"), lambda *_args: None,
            )

        app._build_and_send_dashboard = nested_dashboard
        try:
            # ensure_last owns the chat lock. Nested graph publication must not
            # acquire the same non-reentrant asyncio.Lock a second time.
            result = await asyncio.wait_for(manager.ensure_last(10, 20), timeout=0.5)
            self.assertEqual(result, 111)
            self.assertEqual(events, ["send", "cache"])
            self.assertEqual(manager.graph_id(10, 20), 111)
            self.assertEqual(manager.panel_id(10), 111)
        finally:
            if manager._graph_refresh_task is not None:
                manager._graph_refresh_task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await manager._graph_refresh_task

    async def test_failed_graph_send_does_not_adopt_cache_or_schedule(self):
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        cache = []

        async def send():
            raise RuntimeError("Telegram unavailable")

        with self.assertRaisesRegex(RuntimeError, "Telegram unavailable"):
            await manager.publish_graph_workspace(10, 20, send, lambda: cache.append(True), object())

        self.assertEqual(manager.graph_id(10, 20), None)
        self.assertEqual(manager.panel_id(10), None)
        self.assertEqual(cache, [])
        self.assertIsNone(manager._graph_refresh_task)

    async def test_old_graph_callback_cannot_replace_current_message(self):
        from unittest.mock import AsyncMock
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        manager.adopt_graph(10, 20, 99)
        call = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(id=10), message_id=77)
        )
        edit = AsyncMock()
        send = AsyncMock(return_value=SimpleNamespace(message_id=100))

        async def render():
            await manager.replace_graph_workspace(
                call, 20, edit, send, lambda: None,
                lambda sent: manager.adopt_graph(10, 20, sent.message_id),
            )

        await manager.render_graph(10, 20, render, source_message_id=77)

        edit.assert_not_awaited()
        send.assert_not_awaited()
        self.assertEqual(manager.graph_id(10, 20), 99)

    async def test_retired_graph_callback_cannot_replace_new_text_panel(self):
        from unittest.mock import AsyncMock
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        app.user_dashboard = {20: 99}
        app.chat_dashboard = {10: 99}
        manager = TerminalPanelManager(app)
        call = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(id=10), message_id=77)
        )
        edit = AsyncMock()
        send = AsyncMock(return_value=SimpleNamespace(message_id=100))

        async def render():
            await manager.replace_graph_workspace(
                call, 20, edit, send, lambda: None,
                lambda sent: manager.adopt_graph(10, 20, sent.message_id),
            )

        await manager.render_graph(10, 20, render, source_message_id=77)

        edit.assert_not_awaited()
        send.assert_not_awaited()
        self.assertIsNone(manager.graph_id(10, 20))
        self.assertEqual(app.user_dashboard[20], 99)

    async def test_graph_replacement_retires_then_adopts_fresh_id(self):
        from unittest.mock import AsyncMock
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        manager.adopt_graph(10, 20, 77)
        call = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(id=10), message_id=77)
        )
        order = []
        async def edit():
            order.append("edit")
            raise RuntimeError("message to edit not found")
        async def send():
            order.append("send")
            return SimpleNamespace(message_id=88)
        async def delete(*, chat_id, message_id):
            order.append(("delete", chat_id, message_id))
        app.bot.delete_message = delete

        await manager.render_graph(
            10,
            20,
            lambda: manager.replace_graph_workspace(
                call, 20, edit, send, lambda: None,
                lambda sent: (order.append("adopt"), manager.adopt_graph(10, 20, sent.message_id)),
            ),
            source_message_id=77,
        )

        self.assertEqual(order, ["edit", ("delete", 10, 77), "send", "adopt"])
        self.assertEqual(manager.graph_id(10, 20), 88)

    async def test_ensure_last_replaces_previous_owned_panel_in_place(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)

        new_id = await manager.ensure_last(10, 20)

        self.assertEqual(new_id, 77)
        self.assertEqual(manager.panel_id(10), 77)
        self.assertEqual(app.user_dashboard[20], 77)
        self.assertEqual(app.chat_dashboard[10], 77)
        self.assertEqual(app.refresh_calls, [(10, 20, 77)])
        self.assertEqual(app.render_calls, [])
        self.assertEqual(app.bot.deleted, [])

    async def test_stale_panel_refresh_replaced_once_by_canonical_owner(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)
        async def stale_edit(chat_id, user_id, message_id):
            app.refresh_calls.append((chat_id, user_id, message_id))
            return None
        app._refresh_operator_panel = stale_edit

        result = await manager.ensure_last(10, 20)
        self.assertEqual(result, 101)
        self.assertEqual(app.refresh_calls, [(10, 20, 77)])
        self.assertEqual(app.render_calls, [(10, 20, None, None)])
        self.assertEqual(app.bot.deleted, [(10, 77)])
        self.assertEqual(manager.panel_id(10), 101)

    async def test_failed_replacement_propagates_without_fake_success(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)
        async def missing_message(chat_id, user_id, message_id):
            return None
        async def failed_send(*args, **kwargs):
            raise RuntimeError("Telegram unavailable")
        app._refresh_operator_panel = missing_message
        app._build_and_send_dashboard = failed_send

        with self.assertRaisesRegex(RuntimeError, "Telegram unavailable"):
            await manager.ensure_last(10, 20)
        self.assertEqual(manager.panel_id(10), 77)
        self.assertEqual(app.bot.deleted, [])

    async def test_workspace_source_can_be_preserved_above_fresh_terminal_panel(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)

        new_id = await manager.ensure_last(10, 20, preserve_message_id=77)

        self.assertEqual(new_id, 77)
        self.assertEqual(app.bot.deleted, [])
        self.assertEqual(manager.panel_id(10), 77)

    async def test_start_result_restores_one_panel_after_workspace(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)
        manager.enter_workspace(10)
        restored = []

        async def restore(chat_id, user_id):
            restored.append((chat_id, user_id))
            app.user_dashboard[user_id] = 101
            app.chat_dashboard[chat_id] = 101
            return 101

        app._restore_dashboard_to_bottom = restore
        class FakeCallback:
            def __init__(self, data):
                self.data = data
                self.from_user = SimpleNamespace(id=20)
                self.message = SimpleNamespace(chat=SimpleNamespace(id=10), message_id=88)

        with patch("runtime.ui.telegram.panel_lifecycle.CallbackQuery", FakeCallback):
            await manager.after_event(FakeCallback("v2_quick_start"))
        self.assertEqual(restored, [(10, 20)])
        self.assertEqual(manager.panel_id(10), 101)
        self.assertFalse(manager.in_workspace(10))
        self.assertEqual(app.render_calls, [])
        with patch("runtime.ui.telegram.panel_lifecycle.CallbackQuery", FakeCallback):
            manager.enter_workspace(10)
            await manager.after_event(FakeCallback("v2_battery_start"))
        self.assertEqual(restored, [(10, 20), (10, 20)])
        self.assertFalse(manager.in_workspace(10))

    async def test_equal_message_ids_in_separate_chats_do_not_cross_refresh(self):
        from unittest.mock import AsyncMock
        import asyncio
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        manager.adopt_graph(10, 20, 77)
        manager.adopt_graph(11, 21, 77)
        self.assertEqual(manager._graph_user_by_chat, {10: 20, 11: 21})
        calls = []

        async def refresh(chat_id, user_id, *, force=False):
            calls.append((chat_id, user_id, manager.graph_id(chat_id, user_id)))
            if len(calls) == 2:
                manager._graph_refresh_task.cancel()

        real_sleep = asyncio.sleep

        async def immediate_tick(_seconds):
            await real_sleep(0)

        manager.start_graph_refresh(refresh)
        with patch("runtime.ui.telegram.panel_lifecycle.asyncio.sleep", new=immediate_tick):
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(manager._graph_refresh_task, 2)
        self.assertEqual(calls, [(10, 20, 77), (11, 21, 77)])
        manager.forget_graph(10, 20, 77)
        self.assertNotIn(10, manager._graph_user_by_chat)
        self.assertEqual(manager.graph_id(11, 21), 77)

    async def test_one_periodic_graph_task_after_repeated_panel_publication(self):
        import asyncio
        app = FakeApp()
        manager = TerminalPanelManager(app)

        async def refresh(chat_id, user_id, *, force=False):
            raise AssertionError("No timed edit expected before first 60s tick")

        manager.start_graph_refresh(refresh)
        first = manager._graph_refresh_task
        manager.start_graph_refresh(refresh)
        self.assertIs(manager._graph_refresh_task, first)
        self.assertFalse(first.done())
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first

    async def test_graph_refresh_waits_for_terminal_publish_on_same_chat(self):
        import asyncio
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        entered = asyncio.Event()
        release = asyncio.Event()
        actions = []

        async def restore(chat_id, user_id):
            actions.append("restore_begin")
            entered.set()
            await release.wait()
            manager.adopt_graph(chat_id, user_id, 333)
            actions.append("restore_end")
            return 333

        async def graph_refresh(chat_id, user_id, *, force=False):
            actions.append("graph_edit")
            self.assertEqual((chat_id, user_id), (10, 20))
            self.assertEqual(manager.graph_id(chat_id, user_id), 333)

        app._restore_dashboard_to_bottom = restore
        publish = asyncio.create_task(manager.publish_last(10, 20))
        await asyncio.wait_for(entered.wait(), 2)
        background = asyncio.create_task(
            manager.refresh_graph(10, 20, graph_refresh)
        )
        await asyncio.sleep(0)
        self.assertEqual(actions, ["restore_begin"])
        release.set()
        self.assertEqual(await asyncio.wait_for(publish, 2), 333)
        await asyncio.wait_for(background, 2)
        self.assertEqual(actions, ["restore_begin", "restore_end", "graph_edit"])
        self.assertEqual(manager.panel_id(10), 333)

    async def test_old_graph_id_cannot_erase_newer_published_graph(self):
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        manager.adopt_graph(10, 20, 200)
        manager.adopt_graph(10, 20, 201)
        manager.forget_graph(10, 20, 200)
        self.assertEqual(manager.graph_id(10, 20), 201)
        self.assertEqual(manager.panel_id(10), 201)
        self.assertEqual(app.user_dashboard[20], 201)
        manager.forget_graph(10, 20, 201)
        self.assertIsNone(manager.graph_id(10, 20))
        self.assertIsNone(manager.panel_id(10))

    async def test_graph_open_closes_workspace_and_preserves_periodic_refresh(self):
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        manager.adopt_graph(10, 20, 77)
        manager.enter_workspace(10)

        class FakeCallback:
            def __init__(self):
                self.data = "operator_graph"
                self.from_user = SimpleNamespace(id=20)
                self.message = SimpleNamespace(chat=SimpleNamespace(id=10), message_id=77)

        with patch("runtime.ui.telegram.panel_lifecycle.CallbackQuery", FakeCallback):
            await manager.after_event(FakeCallback())
        edits = []

        async def refresh(chat_id, user_id, *, force=False):
            edits.append((chat_id, user_id))

        await manager.refresh_graph(10, 20, refresh)
        self.assertFalse(manager.in_workspace(10))
        self.assertEqual(edits, [(10, 20)])
        self.assertEqual(manager.panel_id(10), 77)
        self.assertEqual(app.render_calls, [])
        self.assertEqual(app.refresh_calls, [])

    async def test_graph_range_closes_workspace_without_publishing_second_panel(self):
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        manager.adopt_graph(10, 20, 77)
        manager.enter_workspace(10)

        class FakeCallback:
            def __init__(self):
                self.data = "operator_graph_2h"
                self.from_user = SimpleNamespace(id=20)
                self.message = SimpleNamespace(
                    chat=SimpleNamespace(id=10), message_id=77,
                )

        with patch("runtime.ui.telegram.panel_lifecycle.CallbackQuery", FakeCallback):
            await manager.after_event(FakeCallback())
        self.assertFalse(manager.in_workspace(10))
        self.assertEqual(manager.panel_id(10), 77)
        self.assertEqual(app.render_calls, [])
        self.assertEqual(app.refresh_calls, [])

    async def test_graph_refresh_defers_while_an_operator_workspace_is_open(self):
        app = FakeApp()
        app.user_graph_dashboard = {}
        app.chat_graph_dashboard = {}
        manager = TerminalPanelManager(app)
        manager.adopt_graph(10, 20, 555)
        edits = []

        async def refresh(chat_id, user_id, *, force=False):
            edits.append((chat_id, user_id))

        manager.enter_workspace(10)
        await manager.refresh_graph(10, 20, refresh)
        self.assertEqual(edits, [])
        manager.leave_workspace(10)
        await manager.refresh_graph(10, 20, refresh)
        self.assertEqual(edits, [(10, 20)])

    async def test_stale_text_id_never_replaces_authoritative_graph(self):
        app = FakeApp()
        app.user_graph_dashboard = {20: 140}
        app.chat_graph_dashboard = {10: 140}
        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)
        app.user_dashboard[20] = 77
        app.chat_dashboard[10] = 77
        panel_id = await manager.ensure_last(10, 20)
        self.assertEqual(panel_id, 140)
        self.assertEqual(app.refresh_calls, [(10, 20, 140)])
        self.assertEqual(app.render_calls, [])
        self.assertEqual(app.user_dashboard[20], 140)

    async def test_terminal_back_uses_one_graph_restore_not_text_refresh(self):
        app = FakeApp()
        restored = []
        async def restore(chat_id, user_id):
            restored.append((chat_id, user_id))
            app.chat_dashboard[chat_id] = 140
            app.user_dashboard[user_id] = 140
            return 140
        app._restore_dashboard_to_bottom = restore
        manager = TerminalPanelManager(app)
        manager.enter_workspace(10)
        class FakeCallback:
            def __init__(self, data):
                self.data = data
                self.from_user = SimpleNamespace(id=20)
                self.message = SimpleNamespace(chat=SimpleNamespace(id=10), message_id=88)
        with patch("runtime.ui.telegram.panel_lifecycle.CallbackQuery", FakeCallback):
            await manager.after_event(FakeCallback("operator_done"))
        self.assertEqual(restored, [(10, 20)])
        self.assertEqual(app.refresh_calls, [])
        self.assertEqual(app.render_calls, [])
        self.assertEqual(manager.panel_id(10), 140)
        self.assertFalse(manager.in_workspace(10))

    async def test_charge_wizard_callbacks_do_not_append_dashboard(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)
        class FakeCallback:
            def __init__(self, data):
                self.data = data
                self.from_user = SimpleNamespace(id=20)
                self.message = SimpleNamespace(chat=SimpleNamespace(id=10), message_id=88)

        with patch("runtime.ui.telegram.panel_lifecycle.CallbackQuery", FakeCallback):
            for callback in (CHARGE_CALLBACK_DATA, "v2_profile_efb", "v2_bat_intent_recovery"):
                await manager.after_event(FakeCallback(callback))
        self.assertTrue(manager.in_workspace(10))
        self.assertEqual(app.render_calls, [])
        self.assertEqual(app.refresh_calls, [])

    def test_program_live_mix_and_operator_submenus_are_workspace(self):
        for callback in (
            CHARGE_CALLBACK_DATA,
            "v2_batteries",
            "v2_profile_caca",
            "v2_bat_intent_recovery",
            "v2_mix",
            "v2_mix_bat_0",
            "v2_manual_choose",
            "v2_manual_interrupted",
            "v2_sg_menu",
            OFF_CALLBACK_DATA,
            "off_2h",
            "rd_live_mix",
            "rd_live_mix_bat_0",
            "rd_live_mix_status",
            "rd_managed_adopt",
            "rd_managed_adopt_bat_0",
            "rd_managed_adopt_confirm",
            "rd_managed_mix",
            "rd_managed_mix_bat_0",
            "rd_managed_mix_age_1",
            "rd_managed_mix_confirm",
            "rd_managed_mix_status",
            "rd_hands_off_release_confirm",
            "operator_details",
            "operator_more",
            "operator_adopted_stop",
            "operator_managed_mix_stop",
        ):
            with self.subTest(callback=callback):
                self.assertTrue(_is_workspace_callback(callback))

        # Raw legacy read-only callbacks were retired by ERADICATION-07;
        # only their canonical runtime.ui.telegram callback data is workspace.
        for callback in (
            "logs",
            "entities_status",
            "info_full",
            "profile_custom",
            "charge_modes",
            "profile_caca",
            "profile_efb",
            "profile_agm",
            "menu_off",
            "power_toggle",
            "refresh",
            "dash_back",
            "charge_back",
            "operator_done",
            "operator_graph",
            "operator_graph_2h",
            "v2_manual_unbound",
            "v2_battery_start",
            "v2_quick_start",
            "v2_mix_start",
            "rd_live_mix_start_delta_off",
            "rd_managed_adopt_execute",
            "rd_managed_adopt_cancel",
            "rd_managed_mix_execute",
            "rd_managed_mix_cancel",
            "operator_managed_mix_stop_execute",
        ):
            with self.subTest(callback=callback):
                self.assertFalse(_is_workspace_callback(callback))

    def test_workflow_completion_and_cancel_are_terminal(self):
        for callback in (
            "rd_live_mix_start_observe",
            "rd_live_mix_start_delta_off",
            "rd_live_mix_cancel",
            "rd_live_mix_stop_observer",
            "rd_managed_adopt_execute",
            "rd_managed_adopt_cancel",
            "rd_managed_mix_execute",
            "rd_managed_mix_cancel",
            "operator_done",
            "operator_adopted_stop_execute",
            "operator_managed_mix_stop_execute",
            "rd_hands_off_release_execute",
            "rd_hands_off_release_cancel",
            "v2_quick_start",
            "v2_battery_start",
            "v2_mix_start",
            "v2_manual_reauthorize",
            "v2_manual_discard",
        ):
            with self.subTest(callback=callback):
                self.assertIn(callback, _TERMINAL_CALLBACKS)

    def test_workspace_state_is_explicit_per_chat(self):
        manager = TerminalPanelManager(FakeApp())
        self.assertFalse(manager.in_workspace(10))
        manager.enter_workspace(10)
        self.assertTrue(manager.in_workspace(10))
        self.assertFalse(manager.in_workspace(11))
        manager.leave_workspace(10)
        self.assertFalse(manager.in_workspace(10))

    async def test_adopt_updates_both_dashboard_indexes(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)

        panel_id = manager.adopt(10, 20, 55)

        self.assertEqual(panel_id, 55)
        self.assertEqual(app.user_dashboard[20], 55)
        self.assertEqual(app.chat_dashboard[10], 55)
        self.assertEqual(manager.panel_id(10), 55)

    async def test_install_owns_notification_refresh_without_timer(self):
        app = FakeApp()
        manager = install_panel_last(app)

        self.assertIs(app.terminal_panel_manager, manager)
        self.assertEqual(len(app.router.message.middleware), 1)
        self.assertEqual(len(app.router.callback_query.middleware), 1)

        await app._send_notify_safe("critical event", True)
        self.assertEqual(app.notifications, [("critical event", True)])
        self.assertEqual(app.render_calls, [(10, 20, None, None)])
        self.assertEqual(manager.panel_id(10), 101)

    async def test_scheduled_notification_panel_uses_captured_chat_not_latest_chat(self):
        app = FakeApp()
        captured = []

        async def send_with_recipient(
            msg, critical=True, recipient_chat_id=None, recipient_user_id=None
        ):
            captured.append((msg, critical, recipient_chat_id, recipient_user_id))

        app._send_notify_safe = send_with_recipient
        manager = install_panel_last(app)
        app.last_chat_id = 99
        app.last_user_id = 99

        await app._send_notify_safe("scheduled event", True, 10, 20)

        self.assertEqual(captured, [("scheduled event", True, 10, 20)])
        self.assertEqual(app.render_calls, [(10, 20, None, None)])
        self.assertEqual(manager.panel_id(10), 101)
        self.assertIsNone(manager.panel_id(99))

    async def test_notification_does_not_push_panel_under_active_workspace(self):
        app = FakeApp()
        manager = install_panel_last(app)
        manager.enter_workspace(10)

        await app._send_notify_safe("background event", False)

        self.assertEqual(app.notifications, [("background event", False)])
        self.assertEqual(app.render_calls, [])
        self.assertTrue(manager.in_workspace(10))

        manager.leave_workspace(10)
        await app._send_notify_safe("terminal event", False)
        self.assertEqual(app.render_calls, [(10, 20, None, None)])

    async def test_install_is_idempotent(self):
        app = FakeApp()
        first = install_panel_last(app)
        second = install_panel_last(app)

        self.assertIs(first, second)
        self.assertEqual(len(app.router.message.middleware), 1)
        self.assertEqual(len(app.router.callback_query.middleware), 1)

    async def test_middleware_restores_panel_after_successful_handler(self):
        manager = FakeEventManager()
        middleware = PanelLastMiddleware(manager)
        event = object()

        async def handler(received, data):
            self.assertIs(received, event)
            return "ok"

        result = await middleware(handler, event, {})

        self.assertEqual(result, "ok")
        self.assertEqual(manager.events, [event])

    async def test_middleware_restores_panel_then_reraises_original_handler_error(self):
        manager = FakeEventManager()
        middleware = PanelLastMiddleware(manager)
        event = object()

        async def handler(received, data):
            raise RuntimeError("synthetic handler failure")

        with self.assertRaisesRegex(RuntimeError, "synthetic handler failure"):
            await middleware(handler, event, {})

        self.assertEqual(manager.events, [event])


class TerminalTextFallbackReadPortTests(unittest.IsolatedAsyncioTestCase):
    """Failed /start text fallback must not bypass Application's read source."""

    async def _case(self, *, read_error=None):
        from unittest.mock import AsyncMock

        app = FakeApp()
        app.ParseMode = SimpleNamespace(HTML="HTML")
        # Absence of app.hass is intentional: the Telegram publication owner
        # must depend only on the already-authorized read port.
        async def send_message(**kwargs):
            self.sent = kwargs
            return SimpleNamespace(message_id=125)
        app.bot.send_message = send_message

        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)
        fake_port = SimpleNamespace(read_live=AsyncMock(
            side_effect=read_error,
            return_value={"battery_voltage": 12.3},
        ))
        with patch(
            "application.operator_read_source.OperatorReadSource",
            return_value=fake_port,
        ) as constructor, patch(
            "operator_hmi.build_operator_hmi_state",
            return_value="hmi-state",
        ) as build_state, patch(
            "operator_hmi.render_operator_panel", return_value="Degraded panel",
        ), patch(
            "operator_hmi.build_operator_keyboard", return_value="buttons",
        ):
            new_id = await manager.ensure_text_last(10, 20)

        constructor.assert_called_once_with(app)
        fake_port.read_live.assert_awaited_once()
        build_state.assert_called_once_with(
            app, {} if read_error else {"battery_voltage": 12.3},
        )
        self.assertEqual(new_id, 125)
        self.assertEqual(self.sent["text"], "Degraded panel")
        self.assertEqual(self.sent["reply_markup"], "buttons")
        self.assertEqual(self.sent["parse_mode"], "HTML")
        self.assertEqual(manager.panel_id(10), 125)
        self.assertEqual(app.bot.deleted, [(10, 77)])

    async def test_recovery_uses_application_read_port_before_telegram_publication(self):
        await self._case()

    async def test_read_failure_degrades_panel_without_fabricating_live_evidence(self):
        await self._case(read_error=ConnectionError("unavailable"))


if __name__ == "__main__":
    unittest.main()
