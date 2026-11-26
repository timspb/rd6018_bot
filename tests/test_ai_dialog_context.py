import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from runtime import production_runtime


class _Message:
    text = "Покажи состояние"
    chat = SimpleNamespace(id=101)
    from_user = SimpleNamespace(id=7)

    def __init__(self):
        self.answers = []
        self.edits = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return SimpleNamespace(edit_text=self._edit)

    async def _edit(self, text, **kwargs):
        self.edits.append((text, kwargs))


class AiDialogContextTests(unittest.TestCase):
    def test_missing_ai_context_returns_safe_structured_fallback(self):
        class BrokenHass:
            async def get_all_live(self):
                raise RuntimeError("telemetry unavailable")

        with patch.object(production_runtime, "hass", BrokenHass()):
            context = asyncio.run(production_runtime.get_ai_context_dict())
        self.assertEqual(context["output_status"], "UNKNOWN")
        self.assertFalse(context["capacity_known"])

    def test_dialog_uses_one_text_projection_and_only_prompt_override_fields(self):
        message = _Message()
        captured = []

        async def fake_ask(payload):
            captured.append(payload)
            return "Готово"

        async def fake_context():
            return "Контекст недоступен"

        with patch.object(production_runtime, "DEEPSEEK_API_KEY", "configured"), \
                patch.object(production_runtime, "get_ai_context", fake_context), \
                patch.object(production_runtime, "get_ai_context_dict", new_callable=AsyncMock) as unused_context_dict, \
                patch.object(production_runtime, "ask_deepseek", fake_ask):
            asyncio.run(production_runtime.handle_dialog_mode(message))

        unused_context_dict.assert_not_awaited()
        self.assertTrue(message.answers)
        self.assertTrue(message.edits)
        self.assertEqual(len(captured), 1)
        self.assertEqual(set(captured[0]), {"system_prompt_override", "user_prompt_override"})
        self.assertIn("Контекст недоступен", captured[0]["user_prompt_override"])


if __name__ == "__main__":
    unittest.main()
