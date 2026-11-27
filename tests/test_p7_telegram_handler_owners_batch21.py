"""Focused fake-only coverage for the P7 Telegram handler owner cutover."""

from __future__ import annotations

import ast
import asyncio
import html
import pathlib
import unittest
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict
from unittest.mock import AsyncMock

from runtime.ui.telegram.ingress import install_text_message_handler


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _function(path, name, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


class FakeMessage:
    def __init__(self, text="60"):
        self.text = text
        self.from_user = SimpleNamespace(id=7)
        self.chat = SimpleNamespace(id=70)
        self.answers = []
        self.edits = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        async def edit_text(value, **edit_kwargs):
            self.edits.append((value, edit_kwargs))
        return SimpleNamespace(edit_text=edit_text)


class CapacityOwnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = []
        self.message = FakeMessage()

        async def submit(intent):
            self.calls.append(intent)
            return SimpleNamespace(accepted=False, reason="policy denied")

        self.route = SimpleNamespace(submit=submit)
        self.intent_ctor = lambda *args: (args,)
        self.ns = {
            "Any": Any,
            "Dict": Dict,
            "Callable": Callable,
            "StartFeedbackResult": Any,
            "OperatorIntent": self.intent_ctor,
            "OperatorIntentKind": SimpleNamespace(START_CHARGE="START_CHARGE"),
            "BatteryCondition": SimpleNamespace(UNKNOWN="UNKNOWN"),
            "ChargeIntent": SimpleNamespace(NORMAL="NORMAL"),
            "ParseMode": SimpleNamespace(HTML="HTML"),
            "logger": SimpleNamespace(error=lambda *args: None),
            "format_start_feedback": lambda result: "accepted",
        }

    async def _call(self, *, route="present", pending=None):
        handler = _function(ROOT / "runtime/ui/telegram/charge.py", "handle_capacity_input", self.ns)
        await handler(self.message, "AGM", 7, route=self.route if route == "present" else None,
                      pending_intent=pending or {}, parse_mode="HTML", logger=self.ns["logger"],
                      format_start_feedback=lambda result: "accepted")

    async def test_valid_capacity_submits_existing_intent_and_rejection_preserves_state(self):
        pending = {7: "RECOVERY"}
        await self._call(pending=pending)
        self.assertEqual(self.calls[0][0][3]["capacity_ah"], 60)
        self.assertEqual(self.calls[0][0][3]["intent"], "RECOVERY")
        self.assertIn("START отклонён: policy denied", self.message.answers[0][0])
        self.assertEqual(pending, {7: "RECOVERY"})

    async def test_absent_route_explicitly_rejects_without_start(self):
        await self._call(route="absent")
        self.assertFalse(self.calls)
        self.assertIn("START недоступен", self.message.answers[0][0])


class AiDialogOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_message_and_api_errors_are_safe_html_and_logs_hide_secrets(self):
        handler = _function(ROOT / "runtime/ui/telegram/analysis.py", "handle_dialog_delivery", {
            "Any": Any, "Callable": Callable, "Awaitable": Awaitable,
        })
        message = FakeMessage("question")
        await handler(message, ai_available=False, get_context=AsyncMock(), ask=AsyncMock(),
                      system_prompt="system", sanitize=html.escape, parse_mode="HTML",
                      logger=SimpleNamespace(error=lambda *args: self.fail("must not log exception")))
        self.assertEqual(message.answers[0][0], "🤖 AI-консультант недоступен (не настроен API ключ)")

        message = FakeMessage("question")
        async def fail(_payload):
            raise RuntimeError("secret-token")
        log_messages = []
        await handler(message, ai_available=True, get_context=AsyncMock(return_value="ctx"),
                      ask=fail, system_prompt="system", sanitize=html.escape, parse_mode="HTML",
                      logger=SimpleNamespace(error=lambda *args: log_messages.append(args)))
        self.assertEqual(message.edits[-1][0], "🤖 Ошибка при обращении к AI-консультанту.")
        self.assertEqual(message.edits[-1][1]["parse_mode"], "HTML")
        self.assertNotIn("secret-token", repr(log_messages))
        self.assertNotIn("configured-secret", repr(log_messages))

    async def test_error_response_and_success_use_html_sanitization(self):
        handler = _function(ROOT / "runtime/ui/telegram/analysis.py", "handle_dialog_delivery", {
            "Any": Any, "Callable": Callable, "Awaitable": Awaitable,
        })
        for response in ("ERROR: <token>", "ответ <script>"):
            message = FakeMessage("question")
            await handler(message, ai_available=True, get_context=AsyncMock(return_value="ctx"),
                          ask=AsyncMock(return_value=response), system_prompt="system",
                          sanitize=html.escape, parse_mode="HTML",
                          logger=SimpleNamespace(error=lambda *args: None))
            text, kwargs = message.edits[-1]
            self.assertNotIn("<script>", text)
            self.assertEqual(kwargs["parse_mode"], "HTML")
            self.assertEqual(len(message.answers), 1)  # original thinking message semantics
            self.assertEqual(message.answers[0][0], "🤖 Анализирую данные...")
            if response.startswith("ERROR:"):
                self.assertEqual(text, "🤖 ERROR: &lt;token&gt;")
            else:
                self.assertEqual(text, "🤖 <b>AI-Консультант:</b>\r\n\r\nответ &lt;script&gt;")


class RuntimeCompatibilityWrapperTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_wrappers_resolve_rebound_runtime_symbols_each_call(self):
        source = ROOT / "runtime/production_runtime.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        wanted = {"handle_ah_input", "handle_dialog_mode"}
        nodes = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in wanted]
        self.assertEqual({n.name for n in nodes}, wanted)
        namespace = {
            "Message": Any,
            "globals": lambda: namespace,
            "_pending_intent": {7: "RECOVERY"},
            "ParseMode": SimpleNamespace(HTML="HTML"),
            "logger": object(),
            "DEEPSEEK_API_KEY": "key",
            "get_ai_context": object(),
            "ask_deepseek": object(),
            "AI_CONSULTANT_SYSTEM_PROMPT": "prompt",
            "_sanitize_telegram_html": object(),
            "format_start_feedback": lambda _result: "accepted",
        }
        calls = []
        async def delegate(*args, **kwargs):
            calls.append((args, kwargs))
        namespace["handle_capacity_input"] = delegate
        namespace["handle_dialog_delivery"] = delegate
        module = ast.Module(body=nodes, type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, str(source), "exec"), namespace)

        first_route = object()
        namespace["_v3_production_start_route"] = first_route
        await namespace["handle_ah_input"](FakeMessage(), "AGM", 7)
        await namespace["handle_dialog_mode"](FakeMessage())
        namespace["_v3_production_start_route"] = None
        await namespace["handle_ah_input"](FakeMessage(), "EFB", 8)
        self.assertIs(calls[0][1]["route"], first_route)
        self.assertIsNone(calls[2][1]["route"])
        self.assertEqual(calls[0][1]["pending_intent"], namespace["_pending_intent"])
        self.assertTrue(calls[1][1]["ai_available"])


class RegisteredTextDispatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = ROOT / "runtime/production_runtime.py"
        ingress = ROOT / "runtime/ui/telegram/ingress.py"
        source_text = source.read_text(encoding="utf-8")
        self.assertIn("install_text_message_handler(", source_text)
        ingress_tree = ast.parse(ingress.read_text(encoding="utf-8"))
        node = next(n for n in ast.walk(ingress_tree)
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "text_message_handler")
        self.registered_decorator = ast.unparse(node.decorator_list[0])
        self.dialog = AsyncMock()
        self.capacity = AsyncMock()
        self.off = SimpleNamespace(update_from_document=lambda _doc: True)
        self.ns = {
            "Message": Any,
            "_check_chat_and_respond": AsyncMock(return_value=True),
            "awaiting_ah": {},
            "_parse_off_command": lambda text: {"parts": [text]} if text.startswith("off ") else None,
            "_operator_off_conditions": self.off,
            "_save_manual_off_state": lambda: None,
            "_clear_manual_off": lambda: None,
            "ParseMode": SimpleNamespace(HTML="HTML"),
            "last_chat_id": None,
            "handle_ah_input": self.capacity,
            "handle_dialog_mode": self.dialog,
        }
        class Router:
            def message(self, _filter):
                return lambda callback: callback
        self.ns["text_message_handler"] = install_text_message_handler(
            Router(),
            check_chat=self.ns["_check_chat_and_respond"],
            awaiting_capacity=self.ns["awaiting_ah"],
            parse_off_command=self.ns["_parse_off_command"],
            update_condition=self.off.update_from_document,
            save_condition=self.ns["_save_manual_off_state"],
            clear_condition=self.ns["_clear_manual_off"],
            set_last_chat=lambda chat_id: self.ns.__setitem__("last_chat_id", chat_id),
            get_capacity_handler=lambda: self.ns["handle_ah_input"],
            get_dialog_handler=lambda: self.ns["handle_dialog_mode"],
            parse_mode="HTML",
        )

    async def test_single_registered_handler_keeps_off_and_capacity_ahead_of_ai(self):
        self.assertEqual(self.registered_decorator, "router.message(F.text & ~F.text.startswith('/'))")
        off_message = FakeMessage("off 15.5V")
        await self.ns["text_message_handler"](off_message)
        self.dialog.assert_not_awaited()
        self.assertIn("Выключение по условию", off_message.answers[0][0])

        self.ns["awaiting_ah"][7] = "AGM"
        capacity_message = FakeMessage("60")
        await self.ns["text_message_handler"](capacity_message)
        self.capacity.assert_awaited_once_with(capacity_message, "AGM", 7)
        self.dialog.assert_not_awaited()

    async def test_runtime_module_rebinding_keeps_bootstrap_conservative_handler_active(self):
        original = AsyncMock()
        wrapped_calls = []
        self.ns["handle_ah_input"] = original

        async def conservative(message, profile, user_id):
            wrapped_calls.append((profile, user_id))
            self.ns["_pending_intent"].setdefault(user_id, "NORMAL")
            await original(message, profile, user_id)

        # production_bootstrap installs this wrapper by assigning app.handle_ah_input;
        # app is the same module object used as the registered handler's globals.
        bootstrap = (ROOT / "production_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("installed_handle_ah = app.handle_ah_input", bootstrap)
        self.assertIn("app.handle_ah_input = _handle_ah_conservative", bootstrap)
        self.ns["handle_ah_input"] = conservative
        self.ns["_pending_intent"] = {}
        self.ns["awaiting_ah"][7] = "EFB"
        message = FakeMessage("70")
        await self.ns["text_message_handler"](message)
        self.assertEqual(wrapped_calls, [("EFB", 7)])
        self.assertEqual(self.ns["_pending_intent"], {7: "NORMAL"})
        original.assert_awaited_once_with(message, "EFB", 7)


if __name__ == "__main__":
    unittest.main()
