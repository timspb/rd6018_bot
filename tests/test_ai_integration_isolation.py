from __future__ import annotations

import asyncio
import builtins
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from integrations.ai import ask_deepseek
from integrations.ai import engine
from runtime.ui.telegram.analysis import handle_dialog_delivery


class AIIntegrationIsolationTests(unittest.TestCase):
    def test_non_ai_core_imports_without_loading_optional_ai_package(self):
        code = r'''import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "integrations.ai" or name.startswith("integrations.ai."):
        raise AssertionError("core import required optional AI")
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
import application.operator_snapshot_provider
import runtime.production_runtime
import runtime.charge.diagnostics
import charge_controller
assert "integrations.ai" not in __import__("sys").modules
'''
        env = dict(os.environ)
        env.update({"TG_TOKEN": "123456789:TEST_TOKEN_NOT_REAL", "HA_URL": "http://127.0.0.1:8123", "HA_TOKEN": "fake-loopback-token"})
        result = subprocess.run([sys.executable, "-c", code], cwd=os.getcwd(), env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_analysis_adapter_uses_fake_ai_and_read_only_context(self):
        import logging
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from integrations.ai import runtime as ai_runtime

        async def get_live():
            return {"switch": "off", "is_cv": False, "is_cc": False}

        app = SimpleNamespace(
            hass=SimpleNamespace(get_all_live=get_live),
            get_raw_history=lambda **_kwargs: ([], [], []),
            _safe_stage_snapshot=lambda _temp: {},
            get_recent_events=lambda _limit: [],
            _sanitize_telegram_html=lambda text: text,
            _md_to_html=lambda text: text,
            _canonical_bool=lambda _live, _key: False,
            logger=logging.getLogger("ai-test"),
        )
        fake_ask = AsyncMock(return_value="advisory reply")
        with patch.object(ai_runtime, "ask_deepseek", fake_ask):
            result = asyncio.run(ai_runtime.analysis(app))
        self.assertIn("advisory reply", result)
        fake_ask.assert_awaited_once()

    def test_no_key_disables_client_before_http_import(self):
        real_import = builtins.__import__

        def import_without_aiohttp(name, *args, **kwargs):
            if name == "aiohttp":
                raise AssertionError("disabled AI must not load its HTTP client")
            return real_import(name, *args, **kwargs)

        with patch.object(engine, "DEEPSEEK_API_KEY", ""), patch(
            "builtins.__import__", side_effect=import_without_aiohttp
        ):
            result = asyncio.run(ask_deepseek({"user_prompt_override": "hello"}))
        self.assertEqual(result, "DeepSeek API ключ не настроен.")

    def test_missing_http_dependency_reports_ai_unavailable_without_network(self):
        real_import = builtins.__import__

        def import_without_aiohttp(name, *args, **kwargs):
            if name == "aiohttp":
                raise ImportError("test-only missing optional dependency")
            return real_import(name, *args, **kwargs)

        with patch.object(engine, "DEEPSEEK_API_KEY", "inert-test-token"), patch(
            "builtins.__import__", side_effect=import_without_aiohttp
        ):
            result = asyncio.run(ask_deepseek({"user_prompt_override": "hello"}))
        self.assertIn("недоступен", result)

    def test_dialog_disabled_path_does_not_read_context_or_call_ai(self):
        class Message:
            def __init__(self):
                self.answers = []

            async def answer(self, text):
                self.answers.append(text)
                return self

        message = Message()

        async def forbidden():
            raise AssertionError("disabled AI must not request context")

        async def run():
            await handle_dialog_delivery(
                message,
                ai_available=False,
                get_context=forbidden,
                ask=lambda _request: forbidden(),
                system_prompt="prompt",
                sanitize=str,
                parse_mode=None,
                logger=None,
            )

        asyncio.run(run())
        self.assertEqual(len(message.answers), 1)
        self.assertIn("недоступен", message.answers[0])

    def test_compatibility_exports_keep_same_public_callables(self):
        from ai_engine import ask_deepseek as compatibility_ask
        from ai_engine import format_ai_snapshot as compatibility_format
        from integrations.ai import format_ai_snapshot

        self.assertIs(compatibility_ask, ask_deepseek)
        self.assertIs(compatibility_format, format_ai_snapshot)

    def test_prompt_and_runtime_lazy_exports_preserve_identity(self):
        from ai_system_prompt import AI_CONSULTANT_SYSTEM_PROMPT as compatibility_prompt
        from integrations.ai import AI_CONSULTANT_SYSTEM_PROMPT
        from runtime import production_runtime

        self.assertIs(compatibility_prompt, AI_CONSULTANT_SYSTEM_PROMPT)
        self.assertIs(production_runtime.AI_CONSULTANT_SYSTEM_PROMPT, AI_CONSULTANT_SYSTEM_PROMPT)
        self.assertIs(production_runtime.ask_deepseek, ask_deepseek)

    def test_ai_package_has_no_physical_execution_imports(self):
        import ast
        from pathlib import Path

        package = Path(engine.__file__).parent
        forbidden_imports = {"ExecutionPort", "safe_enable_output", "esp_direct", "hass_api"}
        forbidden_calls = {"safe_enable_output", "set_output", "set_voltage", "set_current"}
        for source_path in package.glob("*.py"):
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(source_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = {alias.name.split(".")[0] for alias in node.names}
                    self.assertFalse(imported & forbidden_imports, f"{source_path.name}: {imported & forbidden_imports}")
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn(node.module, forbidden_imports, f"{source_path.name}: {node.module}")
                    self.assertFalse({alias.name for alias in node.names} & forbidden_imports, source_path.name)
                elif isinstance(node, ast.Call):
                    called = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
                    self.assertNotIn(called, forbidden_calls, f"{source_path.name}: {called}")
