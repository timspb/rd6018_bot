"""Fake-first regression for the extracted Telegram recipe selection callbacks."""

from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.ui.telegram.recipe_buttons import install_start_recipe_selection_routes


ROOT = Path(__file__).resolve().parents[1]


class _Router:
    def __init__(self):
        self.handlers = {}

    def callback_query(self, _filter):
        return lambda callback: self.handlers.setdefault(callback.__name__, callback)


@dataclass
class _PendingStart:
    profile: str
    intent: str
    recipe_id: str | None = None
    recipe_version: int | None = None
    native_recipe_name: str | None = None
    native_recipe_version: int | None = None


class RecipeSelectionIngressTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_pick_dispatch_preserves_order_dynamic_catalog_and_shared_state(self):
        router = _Router()
        events = []
        pending = _PendingStart(profile="EFB", intent="NORMAL")
        pending_state = {7: pending}

        class CatalogLibrary:
            def __init__(self, label):
                self.label = label

            def load(self, name, version):
                events.append(("load", self.label, name, version))
                return object()

        class Catalog:
            def __init__(self, label):
                self.label = label
                self.library = CatalogLibrary(label)

            def active_recipes(self):
                events.append(("active_recipes", self.label))
                return ("demo",)

        app = SimpleNamespace(
            router=router,
            _user_recipe_catalog=Catalog("original"),
            _check_chat_and_respond=lambda call: _allow(call),
        )

        async def _allow(_call):
            events.append("permission")
            return True

        async def acknowledge(call, *args, **kwargs):
            events.append(("ack", args, kwargs))

        async def answer(call, text, **kwargs):
            events.append(("answer", text, kwargs))

        install_start_recipe_selection_routes(
            app,
            pending_start=pending_state,
            acknowledge=acknowledge,
            answer=answer,
            preview_keyboard=lambda callback: ("preview", callback),
        )
        self.assertEqual(
            set(router.handlers), {"pick_native_recipe_handler", "pick_recipe_handler"}
        )

        replacement_catalog = Catalog("replacement")
        app._user_recipe_catalog = replacement_catalog
        call = SimpleNamespace(
            data="v2_recipe_pick:demo:3",
            from_user=SimpleNamespace(id=7),
        )
        with patch(
            "runtime.ui.telegram.start_recipe_selection_buttons.inspect_recipe",
            return_value=SimpleNamespace(admissible_structure=True, problems=()),
        ):
            await router.handlers["pick_recipe_handler"](call)

        self.assertEqual(events[0:3], [
            "permission", ("active_recipes", "replacement"),
            ("load", "replacement", "demo", 3),
        ])
        self.assertEqual(events[3][0], "ack")
        self.assertEqual(events[4][0], "answer")
        self.assertEqual(events[4][2]["reply_markup"], ("preview", "v2_battery_start"))
        self.assertEqual(
            (pending_state[7].recipe_id, pending_state[7].recipe_version,
             pending_state[7].native_recipe_name, pending_state[7].native_recipe_version),
            ("demo", 3, None, None),
        )

    def test_production_bot_ui_only_composes_the_recipe_ingress_owner(self):
        source = (ROOT / "production_bot_ui.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        definitions = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("pick_recipe_handler", definitions)
        self.assertNotIn("pick_native_recipe_handler", definitions)
        self.assertIn("install_start_recipe_selection_routes(", source)


if __name__ == "__main__":
    unittest.main()
