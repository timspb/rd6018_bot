from __future__ import annotations

import ast
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from battery_registry import BatteryRecord
from pb_domain import BatteryChemistry, BatteryIdentity, BatteryLifecycle
from runtime.ui.telegram import battery_selection


ROOT = pathlib.Path(__file__).resolve().parents[1]


class Router:
    def __init__(self):
        self.handlers = []

    def callback_query(self, predicate):
        def register(handler):
            self.handlers.append(handler)
            return handler
        return register


class BatteryAddInputLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        battery_selection._battery_pages.clear()

    def install(self, pending, **overrides):
        app = SimpleNamespace(router=Router())
        app._check_chat_and_respond = AsyncMock(return_value=True)
        fallback = AsyncMock()
        deps = dict(
            new_battery_input=pending,
            acknowledge=AsyncMock(),
            answer=AsyncMock(),
            fallback_handler=fallback,
            parse_battery=lambda text: (SimpleNamespace(battery_id="b1", chemistry="AGM"), "life"),
            save_battery=AsyncMock(),
            list_saved_batteries=AsyncMock(return_value=[]),
            format_battery_card=lambda record: "CARD",
            battery_rows=lambda records: [],
            charge_callback_data="v2_charge_modes",
        )
        deps.update(overrides)
        battery_selection.install_battery_add_route(app, **deps)
        return app, deps

    async def test_valid_input_preserves_save_then_clear_then_reload_order(self):
        pending = {73}
        identity = BatteryIdentity("b1", BatteryChemistry.AGM, 70, "Varta", "X")
        record = BatteryRecord(identity=identity, lifecycle=BatteryLifecycle())
        events = []

        async def save(got_identity, lifecycle):
            events.append(("save", got_identity, lifecycle, 73 in pending))

        async def list_records(*, limit):
            events.append(("list", limit, 73 in pending))
            return [record]

        app, deps = self.install(
            pending,
            parse_battery=lambda text: (identity, "life"),
            save_battery=save,
            list_saved_batteries=list_records,
            format_battery_card=lambda got: "CARD:" + got.identity.battery_id,
        )
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=73), text="b1 | AGM | 70 | Varta | X",
            answer=AsyncMock(),
        )

        await app.handle_battery_add_input(message)

        self.assertEqual([("save", identity, "life", True), ("list", 50, False)], events)
        self.assertEqual(set(), pending)
        self.assertEqual([record], battery_selection._battery_pages[73])
        message.answer.assert_awaited_once()
        markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(
            ["v2_battery_add", "v2_charge_modes"],
            [row[0].callback_data for row in markup.inline_keyboard],
        )
        deps["fallback_handler"].assert_not_awaited()

    async def test_parse_failure_retains_pending_input_and_reports_format(self):
        pending = {73}
        app, deps = self.install(
            pending,
            parse_battery=lambda text: (_ for _ in ()).throw(ValueError("invalid <battery>")),
        )
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=73), text="bad", answer=AsyncMock(),
        )

        await app.handle_battery_add_input(message)

        self.assertEqual({73}, pending)
        self.assertIn("invalid &lt;battery&gt;", message.answer.await_args.args[0])
        deps["save_battery"].assert_not_awaited()
        deps["list_saved_batteries"].assert_not_awaited()

    async def test_non_add_text_delegates_to_captured_dialog_handler(self):
        app, deps = self.install(set())
        message = SimpleNamespace(from_user=SimpleNamespace(id=74), text="hello")

        await app.handle_battery_add_input(message)

        deps["fallback_handler"].assert_awaited_once_with(message)

    async def test_existing_add_callback_still_checks_chat_acknowledges_and_prompts(self):
        pending = set()
        app, deps = self.install(pending)
        call = SimpleNamespace(from_user=SimpleNamespace(id=73))

        await app._battery_add_handler(call)

        app._check_chat_and_respond.assert_awaited_once_with(call)
        deps["acknowledge"].assert_awaited_once_with(call)
        self.assertEqual({73}, pending)
        deps["answer"].assert_awaited_once_with(
            call,
            "<b>➕ Добавление АКБ</b>\n\n"
            "Одним сообщением:\n"
            "<code>ID | AGM/EFB/Ca/Ca | Ah | Производитель | Модель</code>\n\n"
            "Например:\n<code>varta70 | AGM | 70 | Varta | Silver Dynamic AGM</code>",
        )

    def test_production_supplies_the_existing_owner_contract(self):
        source = (ROOT / "production_bot_ui.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        installer = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                         and node.name == "install_ui_support")
        call = next(node for node in ast.walk(installer) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "install_battery_add_route")
        supplied = {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords}
        self.assertEqual({
            "new_battery_input": "_new_battery_input",
            "acknowledge": "_ack_callback",
            "answer": "answer",
            "fallback_handler": "original_handle_dialog",
            "parse_battery": "parse_battery",
            "save_battery": "save_battery",
            "list_saved_batteries": "list_batteries",
            "format_battery_card": "format_battery_card",
            "battery_rows": "_battery_rows",
            "charge_callback_data": "CHARGE_CALLBACK_DATA",
        }, supplied)
        self.assertIn("app.handle_dialog_mode = app.handle_battery_add_input", source)


if __name__ == "__main__":
    unittest.main()
