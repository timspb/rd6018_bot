"""Fake-only parity checks for the production Telegram text fallback contract.

The production module is deliberately not imported: only selected function AST
declarations are compiled with decorators removed and executed against fakes.
"""
import ast
import asyncio
import logging
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from runtime.operator.off_conditions import OperatorOffConditions
from runtime.ui.telegram.ingress import install_text_message_handler


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = ROOT / "runtime" / "production_runtime.py"


class FakeMessage:
    def __init__(self, text, user_id=7, chat_id=70):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=chat_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        answer = SimpleNamespace(text=text, kwargs=kwargs, edits=[])
        async def edit_text(value, **edit_kwargs):
            answer.edits.append((value, edit_kwargs))
        answer.edit_text = edit_text
        self.answers.append(answer)
        return answer






def load_selected_functions():
    namespace = {
        "Message": FakeMessage,
        "_check_chat_and_respond": AsyncMock(return_value=True),
        "_parse_off_command": lambda _text: None,
        "_clear_manual_off": lambda: None,
        "_save_manual_off_state": lambda: None,
        "logger": logging.getLogger(__name__),
        "ParseMode": SimpleNamespace(HTML="HTML"),
        "awaiting_ah": {},
        "_operator_off_conditions": OperatorOffConditions(),
        "manual_off_saved": 0,
        "manual_off_cleared": 0,
        "last_chat_id": None,
        "_manual_route": None,
        "OperatorIntent": lambda *args, **kwargs: (args, kwargs),
        "OperatorIntentKind": SimpleNamespace(START_CHARGE="START_CHARGE"),
        "_pending_intent": {},
        "ChargeIntent": SimpleNamespace(NORMAL="NORMAL"),
        "BatteryCondition": SimpleNamespace(UNKNOWN="UNKNOWN"),
    }
    namespace["_save_manual_off_state"] = lambda: namespace.__setitem__("manual_off_saved", namespace["manual_off_saved"] + 1)
    namespace["_clear_manual_off"] = lambda: namespace.__setitem__("manual_off_cleared", namespace["manual_off_cleared"] + 1)
    class FakeRouter:
        def message(self, _filter):
            return lambda callback: callback
    namespace["text_message_handler"] = install_text_message_handler(
        FakeRouter(),
        check_chat=namespace["_check_chat_and_respond"],
        awaiting_capacity=namespace["awaiting_ah"],
        parse_off_command=lambda text: namespace["_parse_off_command"](text),
        update_condition=namespace["_operator_off_conditions"].update_from_document,
        save_condition=namespace["_save_manual_off_state"],
        clear_condition=namespace["_clear_manual_off"],
        set_last_chat=lambda chat_id: namespace.__setitem__("last_chat_id", chat_id),
        get_capacity_handler=lambda: namespace["handle_ah_input"],
        get_dialog_handler=lambda: namespace["handle_dialog_mode"],
        parse_mode="HTML",
    )
    return namespace


class TextIngressRetirementTests(unittest.TestCase):
    def test_legacy_numeric_actuator_fallback_is_absent_and_middleware_is_composed(self):
        runtime = RUNTIME_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("async def text_message_handler", runtime)
        ingress_path = ROOT / "runtime" / "ui" / "telegram" / "ingress.py"
        ingress = ingress_path.read_text(encoding="utf-8")
        handler = next(node for node in ast.walk(ast.parse(ingress))
                       if isinstance(node, ast.AsyncFunctionDef) and node.name == "text_message_handler")
        handler_source = ast.get_source_segment(ingress, handler) or ""
        self.assertNotIn("program_voltage_current", handler_source)
        self.assertNotIn("_parse_two_numbers", handler_source)
        self.assertNotIn("_parse_three_values", handler_source)
        bootstrap = (ROOT / "production_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("install_manual_text(app)", bootstrap)
        self.assertIn("_retired_numeric_manual_input", (ROOT / "manual_text.py").read_text(encoding="utf-8"))


    def test_unreachable_custom_wizard_state_and_handler_are_absent(self):
        source = RUNTIME_SOURCE.read_text(encoding="utf-8")
        for retired in (
            "custom_mode_state",
            "custom_mode_data",
            "custom_mode_confirm",
            "handle_custom_mode_input",
        ):
            self.assertNotIn(retired, source)
        self.assertNotIn("custom_mode_state", (ROOT / "manual_text.py").read_text(encoding="utf-8"))


class TextIngressContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = load_selected_functions()

    async def dispatch(self, message):
        await self.ns["text_message_handler"](message)

    async def test_permission_denial_and_slash_command_stop_before_dispatch(self):
        denied = FakeMessage("hello")
        self.ns["_check_chat_and_respond"].return_value = False
        await self.dispatch(denied)
        self.assertEqual(denied.answers, [])

        self.ns = load_selected_functions()
        slash = FakeMessage("/stop")
        await self.dispatch(slash)
        self.assertEqual(slash.answers, [])
        self.assertEqual(self.ns["_check_chat_and_respond"].await_count, 1)

    async def test_exact_off_clears_persisted_condition_without_actuation(self):
        msg = FakeMessage(" off ")
        await self.dispatch(msg)
        self.assertEqual(self.ns["manual_off_cleared"], 1)
        self.assertEqual(self.ns["manual_off_saved"], 0)
        self.assertIn("Сброс условия", msg.answers[0].text)

    async def test_off_condition_is_persisted_without_immediate_off_action(self):
        parsed = {"voltage_ge": 15.5, "voltage_le": None, "current_le": None,
                  "current_ge": None, "time_sec": None, "start_time": 123.0,
                  "parts": ["15.5V"]}
        self.ns["_parse_off_command"] = lambda text: parsed if text.lower().startswith("off ") else None
        self.ns["handle_dialog_mode"] = AsyncMock()
        msg = FakeMessage("off 15.5V")
        await self.dispatch(msg)
        self.assertEqual(self.ns["_operator_off_conditions"].voltage_ge, 15.5)
        self.assertEqual(self.ns["manual_off_saved"], 1)
        self.assertEqual(self.ns["manual_off_cleared"], 0)
        self.assertIn("Выключение по условию", msg.answers[0].text)
        self.ns["handle_dialog_mode"].assert_not_awaited()

    async def test_capacity_route_precedes_free_text_dialog(self):
        self.ns["awaiting_ah"][7] = "AGM"
        self.ns["handle_ah_input"] = AsyncMock()
        self.ns["handle_dialog_mode"] = AsyncMock()
        msg = FakeMessage("60")
        await self.dispatch(msg)
        self.ns["handle_ah_input"].assert_awaited_once_with(msg, "AGM", 7)
        self.assertEqual(msg.answers, [])
        self.ns["handle_dialog_mode"].assert_not_awaited()

    async def test_unmatched_text_falls_through_to_dialog(self):
        self.ns["handle_dialog_mode"] = AsyncMock()
        msg = FakeMessage("hello there")
        await self.dispatch(msg)
        self.ns["handle_dialog_mode"].assert_awaited_once_with(msg)


if __name__ == "__main__":
    unittest.main()
