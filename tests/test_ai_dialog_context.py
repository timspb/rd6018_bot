import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot_legacy


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

        with patch.object(bot_legacy, "hass", BrokenHass()):
            context = asyncio.run(bot_legacy.get_ai_context_dict())
        self.assertEqual(context["output_status"], "UNKNOWN")
        self.assertFalse(context["capacity_known"])

    def test_handle_dialog_mode_has_no_name_error_for_structured_context(self):
        message = _Message()

        async def fake_ask(_payload):
            return "Готово"

        async def fake_context():
            return "Контекст недоступен"

        async def fake_context_dict():
            return {"output_status": "UNKNOWN"}

        with patch.object(bot_legacy, "DEEPSEEK_API_KEY", "configured"), \
                patch.object(bot_legacy, "get_ai_context", fake_context), \
                patch.object(bot_legacy, "get_ai_context_dict", fake_context_dict), \
                patch.object(bot_legacy, "ask_deepseek", fake_ask), \
                patch.object(bot_legacy, "schedule_dashboard_after_60"):
            asyncio.run(bot_legacy.handle_dialog_mode(message))

        self.assertTrue(message.answers)


if __name__ == "__main__":
    unittest.main()
