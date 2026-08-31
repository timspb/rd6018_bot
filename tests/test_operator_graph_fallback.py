import asyncio
import io
import types
import unittest

import operator_hmi as hmi
from operator_dashboard import install_operator_graph_dashboard


class FailingEditBot:
    def __init__(self, *, fail_delete=False):
        self.deleted = []
        self.fail_delete = fail_delete
        self.media_edits = []
        self.caption_edits = []

    async def edit_message_media(self, **kwargs):
        self.media_edits.append(kwargs)
        raise RuntimeError("synthetic edit media failure")

    async def edit_message_caption(self, **kwargs):
        self.caption_edits.append(kwargs)
        raise RuntimeError("synthetic edit caption failure")

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))
        if self.fail_delete:
            raise RuntimeError("synthetic delete failure")
        return True


class FakeMessage:
    def __init__(self):
        self.chat = types.SimpleNamespace(id=10)
        self.message_id = 77
        self.photo_answers = []
        self.text_answers = []

    async def answer_photo(self, *args, **kwargs):
        self.photo_answers.append((args, kwargs))
        return types.SimpleNamespace(message_id=78)

    async def answer(self, *args, **kwargs):
        self.text_answers.append((args, kwargs))
        return types.SimpleNamespace(message_id=78)


class FakeApp:
    CHART_RANGE_30M = "30m"
    CHART_RANGE_2H = "2h"
    CHART_RANGE_SESSION = "session"

    def __init__(self, *, graph=True, fail_delete=False):
        self.bot = FailingEditBot(fail_delete=fail_delete)
        self.asyncio = asyncio
        self.ParseMode = types.SimpleNamespace(HTML="HTML")
        self.BufferedInputFile = lambda payload, filename: (payload, filename)
        self.InputMediaPhoto = lambda **kwargs: kwargs
        self.user_chart_range = {1: self.CHART_RANGE_2H}
        self.user_dashboard = {}
        self.chat_dashboard = {}
        self.graph = graph
        self.rd_control_mode_manager = types.SimpleNamespace(hands_off=False)
        self.rd_live_mix_observer = None
        self.charge_controller = types.SimpleNamespace(
            is_active=False,
            current_stage="Idle",
            battery_type="",
            ah_capacity=0,
        )
        self.manual_session_manager = types.SimpleNamespace(is_active=False)

    def _chart_range_for_user(self, user_id):
        return self.user_chart_range.get(user_id, self.CHART_RANGE_30M)

    def _chart_query_params(self, user_id):
        return self._chart_range_for_user(user_id), None, 120

    async def get_graph_data_with_temp(self, *, limit, since_timestamp):
        if self.graph:
            return [1, 2], [13.0, 13.1], [1.0, 0.9], [25.0, 25.1]
        return [], [], [], []

    def generate_chart(self, times, voltages, currents, temps):
        if not self.graph:
            return None
        return io.BytesIO(b"png")


class OperatorGraphFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, app):
        call = types.SimpleNamespace(message=FakeMessage())
        old_builder = hmi.build_operator_hmi_state
        old_panel = hmi.render_operator_panel
        old_details = hmi.render_operator_details
        old_graph = hmi._render_graph_workspace
        try:
            install_operator_graph_dashboard(app)
            await hmi._render_graph_workspace(app, call, 1)
        finally:
            hmi.build_operator_hmi_state = old_builder
            hmi.render_operator_panel = old_panel
            hmi.render_operator_details = old_details
            hmi._render_graph_workspace = old_graph
        return call

    async def test_failed_media_edit_retires_old_workspace_before_photo_replacement(self):
        app = FakeApp(graph=True)
        call = await self._run(app)

        self.assertEqual(app.bot.deleted, [(10, 77)])
        self.assertEqual(len(call.message.photo_answers), 1)
        self.assertEqual(call.message.text_answers, [])

    async def test_failed_empty_graph_caption_edit_retires_old_workspace_before_text_replacement(self):
        app = FakeApp(graph=False)
        call = await self._run(app)

        self.assertEqual(app.bot.deleted, [(10, 77)])
        self.assertEqual(len(call.message.text_answers), 1)
        self.assertEqual(call.message.photo_answers, [])

    async def test_delete_failure_still_returns_reachable_replacement_workspace(self):
        app = FakeApp(graph=True, fail_delete=True)
        call = await self._run(app)

        self.assertEqual(app.bot.deleted, [(10, 77)])
        self.assertEqual(len(call.message.photo_answers), 1)


if __name__ == "__main__":
    unittest.main()
