"""The installed graph and range callbacks share one terminal-panel owner."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import operator_hmi


class _Router:
    def __init__(self):
        self.handlers = {}

    def callback_query(self, _filter):
        def install(handler):
            self.handlers[handler.__name__] = handler
            return handler
        return install


class _App:
    CHART_RANGE_VALUES = ("30m", "2h", "session")

    def __init__(self, owner):
        self.router = _Router()
        self.terminal_panel_manager = owner
        self.user_chart_range = {}
        self.operator_interface = None
        self._operator_hmi_installed = False
        self.checks = []

    async def _check_chat_and_respond(self, call):
        self.checks.append(call.data)
        return True


def _call(data):
    call = NS(
        data=data, from_user=NS(id=22),
        message=NS(chat=NS(id=11)),
    )
    call.answer = AsyncMock()
    return call


class GraphDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_graph_and_range_both_go_through_terminal_owner(self):
        graph_renders = []
        class Owner:
            async def render_graph(self, chat_id, user_id, render):
                graph_renders.append((chat_id, user_id))
                await render()
        app = _App(Owner())
        operator_hmi.install_operator_hmi(app)
        with patch.object(operator_hmi, "_render_graph_workspace", new_callable=AsyncMock) as render:
            open_call = _call("operator_graph")
            range_call = _call("operator_graph_2h")
            await app.router.handlers["_operator_graph"](open_call)
            await app.router.handlers["_operator_graph_range"](range_call)
        self.assertEqual(graph_renders, [(11, 22), (11, 22)])
        self.assertEqual(render.await_count, 2)
        self.assertEqual(app.user_chart_range[22], "2h")
        self.assertEqual(open_call.answer.await_count, 1)
        self.assertEqual(range_call.answer.await_count, 1)

    async def test_without_terminal_owner_uses_same_existing_renderer(self):
        app = _App(None)
        operator_hmi.install_operator_hmi(app)
        with patch.object(operator_hmi, "_render_graph_workspace", new_callable=AsyncMock) as render:
            await app.router.handlers["_operator_graph"](_call("operator_graph"))
            await app.router.handlers["_operator_graph_range"](_call("operator_graph_session"))
        self.assertEqual(render.await_count, 2)
        self.assertEqual(app.user_chart_range[22], "session")

    async def test_invalid_range_rejected_without_render_or_mutation(self):
        app = _App(None)
        operator_hmi.install_operator_hmi(app)
        call = _call("operator_graph_invalid")
        with patch.object(operator_hmi, "_render_graph_workspace", new_callable=AsyncMock) as render:
            await app.router.handlers["_operator_graph_range"](call)
        render.assert_not_awaited()
        self.assertEqual(app.user_chart_range, {})
        call.answer.assert_awaited_once()
        self.assertTrue(call.answer.await_args.kwargs["show_alert"])
