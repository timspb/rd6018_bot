import builtins
import subprocess
import sys
import unittest
from unittest.mock import patch

from integrations.ai import engine


class _Response:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self):
        return {"choices": [{"message": {"content": "bounded advisory"}}]}

    async def text(self):
        return ""


class _Session:
    last_request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def post(self, url, **kwargs):
        type(self).last_request = (url, kwargs)
        return _Response()


class _Timeout:
    def __init__(self, *, total):
        self.total = total


class OptionalAIEngineTests(unittest.IsolatedAsyncioTestCase):
    def test_importing_engine_does_not_import_http_client_or_dialog_adapter(self):
        script = (
            "import builtins, sys; original = builtins.__import__; "
            "builtins.__import__ = lambda name, *a, **k: "
            "(_ for _ in ()).throw(AssertionError('eager aiohttp')) "
            "if name == 'aiohttp' else original(name, *a, **k); "
            "import integrations.ai.engine; "
            "assert 'integrations.ai.telegram_dialog' not in sys.modules"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    async def test_empty_key_returns_before_attempting_aiohttp_import(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "aiohttp":
                raise AssertionError("aiohttp imported with empty API key")
            return original_import(name, *args, **kwargs)

        with patch.object(engine, "DEEPSEEK_API_KEY", ""), patch(
            "builtins.__import__", side_effect=guarded_import
        ):
            result = await engine.ask_deepseek({"user_prompt_override": "question"})
        self.assertEqual(result, "DeepSeek API ключ не настроен.")

    async def test_missing_http_client_is_a_harmless_configured_result(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "aiohttp":
                raise ImportError("test isolation")
            return original_import(name, *args, **kwargs)

        with patch.object(engine, "DEEPSEEK_API_KEY", "configured"), patch(
            "builtins.__import__", side_effect=guarded_import
        ):
            result = await engine.ask_deepseek({"user_prompt_override": "question"})
        self.assertEqual(result, "AI-консультант недоступен (HTTP-клиент не установлен).")

    async def test_dialogue_payload_and_analysis_response_with_fake_http(self):
        fake_http = type(
            "FakeAiohttp",
            (),
            {"ClientSession": _Session, "ClientTimeout": _Timeout, "ClientError": OSError},
        )
        with patch.dict(sys.modules, {"aiohttp": fake_http}), patch.object(
            engine, "DEEPSEEK_API_KEY", "test-key"
        ), patch.object(engine, "DEEPSEEK_BASE_URL", "https://example.invalid/"):
            answer = await engine.ask_deepseek(
                {
                    "system_prompt_override": "system",
                    "user_prompt_override": "dialogue",
                }
            )
            self.assertEqual(answer, "bounded advisory")
            url, kwargs = _Session.last_request
            payload = kwargs["json"]
            self.assertEqual(url, "https://example.invalid/v1/chat/completions")
            self.assertEqual(payload["messages"], [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "dialogue"},
            ])
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
            self.assertEqual(kwargs["timeout"].total, 30)

            answer = await engine.ask_deepseek(
                {
                    "times": ["t1"],
                    "voltages": [14.2],
                    "currents": [2.1],
                    "ai_context": {"output_status": "ON"},
                    "controller_snapshot": {
                        "safety": {"ovp_offset_v": 0.4, "ocp_offset_a": 1.2}
                    },
                }
            )
            self.assertEqual(answer, "bounded advisory")
            _url, kwargs = _Session.last_request
            analysis_messages = kwargs["json"]["messages"]
            self.assertIn("OVP/OCP +0.4V/+1.2A", analysis_messages[1]["content"])
            self.assertIn("Дополнительно для кнопки AI-анализа", analysis_messages[0]["content"])

    def test_legacy_imports_are_same_owner_and_integrations_package_stays_lazy(self):
        import ai_engine

        self.assertIs(ai_engine.ask_deepseek, engine.ask_deepseek)
        self.assertIs(ai_engine.format_ai_snapshot, engine.format_ai_snapshot)
        self.assertIs(ai_engine.format_recent_events, engine.format_recent_events)
        self.assertIs(engine.format_ai_snapshot, __import__("integrations.ai", fromlist=["format_ai_snapshot"]).format_ai_snapshot)


if __name__ == "__main__":
    unittest.main()
