"""Non-accepted routed intents never execute preserved Telegram actions."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from runtime.ui.commands.models import CommandResult, CommandStatus
from operator_hmi import install_operator_hmi

class Router:
    def __init__(self): self.handlers={}
    def callback_query(self, unused):
        def register(handler):
            self.handlers[handler.__name__]=handler
            return handler
        return register

class App:
    CHART_RANGE_VALUES=("30m","2h","session")
    def __init__(self,status):
        self.router=Router()
        self._operator_hmi_installed=False
        self.operator_interface=NS(submit_intent=AsyncMock(return_value=CommandResult(status,"fixture")))
        self._check_chat_and_respond=AsyncMock(return_value=True)
        self._operator_pause_toggle=AsyncMock()
        self._operator_pause_active=lambda: False
        self.user_chart_range={}
        self.terminal_panel_manager=None

def callback(data):
    call=NS(data=data,from_user=NS(id=7),message=NS(chat=NS(id=8)))
    call.answer=AsyncMock()
    call.message.answer=AsyncMock()
    return call

class IntentStatusGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_must_not_execute_when_safety_blocks_or_confirmation_required(self):
        for status in (CommandStatus.REJECTED, CommandStatus.BLOCKED_BY_SAFETY,
                       CommandStatus.REQUIRES_CONFIRMATION):
            with self.subTest(status=status):
                app=App(status)
                install_operator_hmi(app)
                call=callback("operator_pause_toggle")
                await app.router.handlers["_operator_pause_toggle_handler"](call)
                app._operator_pause_toggle.assert_not_awaited()
                call.answer.assert_awaited_once()
                self.assertTrue(call.answer.await_args.kwargs["show_alert"])

    async def test_read_actions_reject_nonaccepted_without_render(self):
        for status in (CommandStatus.REJECTED, CommandStatus.BLOCKED_BY_SAFETY,
                       CommandStatus.REQUIRES_CONFIRMATION):
            with self.subTest(status=status):
                app=App(status)
                install_operator_hmi(app)
                with patch("operator_hmi._render_graph_workspace", new_callable=AsyncMock) as graph:
                    call=callback("operator_graph")
                    await app.router.handlers["_operator_graph"](call)
                    graph.assert_not_awaited()
                call.answer.assert_awaited_once()
                self.assertTrue(call.answer.await_args.kwargs["show_alert"])

    async def test_accepted_routes_keep_preserved_execution_and_ack(self):
        app=App(CommandStatus.ACCEPTED)
        install_operator_hmi(app)
        call=callback("operator_pause_toggle")
        await app.router.handlers["_operator_pause_toggle_handler"](call)
        app._operator_pause_toggle.assert_awaited_once_with(call)
        call.answer.assert_awaited_once()
