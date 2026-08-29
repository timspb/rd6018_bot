import unittest

from telegram_panel import TerminalPanelManager, install_panel_last


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

    async def test_install_is_idempotent(self):
        app = FakeApp()
        first = install_panel_last(app)
        second = install_panel_last(app)

        self.assertIs(first, second)
        self.assertEqual(len(app.router.message.middleware), 1)
        self.assertEqual(len(app.router.callback_query.middleware), 1)


if __name__ == "__main__":
    unittest.main()
