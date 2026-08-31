import unittest

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
    async def test_ensure_last_publishes_fresh_panel_and_removes_previous_owned_panel(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)

        new_id = await manager.ensure_last(10, 20)

        self.assertEqual(new_id, 101)
        self.assertEqual(manager.panel_id(10), 101)
        self.assertEqual(app.user_dashboard[20], 101)
        self.assertEqual(app.chat_dashboard[10], 101)
        self.assertEqual(app.render_calls, [(10, 20, None, None)])
        self.assertEqual(app.bot.deleted, [(10, 77)])

    async def test_workspace_source_can_be_preserved_above_fresh_terminal_panel(self):
        app = FakeApp()
        manager = TerminalPanelManager(app)
        manager.adopt(10, 20, 77)

        new_id = await manager.ensure_last(10, 20, preserve_message_id=77)

        self.assertEqual(new_id, 101)
        self.assertEqual(app.bot.deleted, [])
        self.assertEqual(manager.panel_id(10), 101)

    def test_program_live_mix_and_operator_submenus_are_workspace(self):
        for callback in (
            "charge_modes",
            "v2_batteries",
            "v2_profile_caca",
            "v2_bat_intent_recovery",
            "v2_mix",
            "v2_mix_bat_0",
            "v2_manual_choose",
            "v2_manual_interrupted",
            "v2_sg_menu",
            "logs",
            "info_full",
            "entities_status",
            "menu_off",
            "off_2h",
            "profile_custom",
            "rd_live_mix",
            "rd_live_mix_bat_0",
            "rd_live_mix_status",
            "rd_hands_off_release_confirm",
            "operator_details",
            "operator_graph",
            "operator_graph_2h",
            "operator_more",
            "operator_adopted_stop",
        ):
            with self.subTest(callback=callback):
                self.assertTrue(_is_workspace_callback(callback))

        for callback in (
            "power_toggle",
            "refresh",
            "dash_back",
            "operator_done",
            "v2_battery_start",
            "v2_quick_start",
            "v2_mix_start",
            "rd_live_mix_start_delta_off",
        ):
            with self.subTest(callback=callback):
                self.assertFalse(_is_workspace_callback(callback))

    def test_workflow_completion_and_cancel_are_terminal(self):
        for callback in (
            "rd_live_mix_start_observe",
            "rd_live_mix_start_delta_off",
            "rd_live_mix_cancel",
            "rd_live_mix_stop_observer",
            "operator_done",
            "operator_adopted_stop_execute",
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

    async def test_install_disables_legacy_delayed_refresh_and_wraps_notifications(self):
        app = FakeApp()
        manager = install_panel_last(app)

        self.assertIs(app.terminal_panel_manager, manager)
        self.assertEqual(len(app.router.message.middleware), 1)
        self.assertEqual(len(app.router.callback_query.middleware), 1)

        app.schedule_dashboard_after_60(10, 20)
        self.assertEqual(app.scheduled, [])

        await app._send_notify_safe("critical event", True)
        self.assertEqual(app.notifications, [("critical event", True)])
        self.assertEqual(app.render_calls, [(10, 20, None, None)])
        self.assertEqual(manager.panel_id(10), 101)

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


if __name__ == "__main__":
    unittest.main()
