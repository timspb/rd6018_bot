import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from integrations.ai.telegram_dialog import handle_dialog_delivery


class _Message:
    def __init__(self, text):
        self.text = text
        self.calls = []

    async def answer(self, text, **kwargs):
        self.calls.append(("answer", text, kwargs))
        return SimpleNamespace(edit_text=self._edit_text)

    async def _edit_text(self, text, **kwargs):
        self.calls.append(("edit", text, kwargs))


class TelegramDialogTests(unittest.IsolatedAsyncioTestCase):
    def make_dependencies(self, response="ok"):
        ask = AsyncMock(return_value=response)
        get_context = AsyncMock(return_value="контекст")
        get_ai_context_dict = AsyncMock(return_value={"output_status": "OFF"})
        get_controller_snapshot = Mock(return_value={"stage": "Idle"})
        get_recent_events = Mock(return_value=["событие"])
        sanitize = Mock(side_effect=lambda value: value.replace("<", "&lt;").replace(">", "&gt;"))
        logger = Mock()
        return {
            "ai_available": True,
            "get_context": get_context,
            "get_ai_context_dict": get_ai_context_dict,
            "get_controller_snapshot": get_controller_snapshot,
            "get_recent_events": get_recent_events,
            "ask": ask,
            "system_prompt": "system",
            "sanitize": sanitize,
            "parse_mode": "HTML",
            "logger": logger,
        }

    async def test_disabled_key_answers_without_reading_context_or_calling_ai(self):
        message = _Message("вопрос")
        deps = self.make_dependencies()
        deps["ai_available"] = False

        await handle_dialog_delivery(message, **deps)

        self.assertEqual(message.calls, [("answer", "🤖 AI-консультант недоступен (не настроен API ключ)", {})])
        deps["get_context"].assert_not_awaited()
        deps["ask"].assert_not_awaited()

    async def test_empty_input_is_ignored(self):
        message = _Message("  \n ")
        deps = self.make_dependencies()

        await handle_dialog_delivery(message, **deps)

        self.assertEqual(message.calls, [])
        deps["ask"].assert_not_awaited()

    async def test_normal_response_preserves_prompt_payload_and_html_delivery(self):
        message = _Message("  Состояние?  ")
        deps = self.make_dependencies("<b>Ответ</b>\nстрока")

        await handle_dialog_delivery(message, **deps)

        self.assertEqual(message.calls, [
            ("answer", "🤖 Анализирую данные...", {}),
            ("edit", "🤖 <b>AI-Консультант:</b>\n\n&lt;b&gt;Ответ&lt;/b&gt;\nстрока", {"parse_mode": "HTML"}),
        ])
        payload = deps["ask"].await_args.args[0]
        self.assertEqual(payload["user_question"], "Состояние?")
        self.assertEqual(payload["ai_context"], {"output_status": "OFF"})
        self.assertEqual(payload["controller_snapshot"], {"stage": "Idle"})
        self.assertEqual(payload["recent_events"], ["событие"])
        self.assertEqual(payload["system_prompt_override"], "system")
        self.assertEqual(payload["user_prompt_override"], """=== ПОЛНЫЙ СЛЕПОК RD6018 ===
контекст

=== ВОПРОС ПОЛЬЗОВАТЕЛЯ ===
Состояние?

=== КАК ОТВЕЧАТЬ ===
1. Сначала дай прямой ответ на вопрос.
2. Если вопрос про текущий этап, время на минимальном токе или переход, используй только факты из контекста, hold-снимка и таймеров.
3. Не называй ток "минимальным", если hold-снимок не активен или rule_met = NO.
4. Не делай общих прогнозов и не уходи в рассуждения.
5. Если данных не хватает, скажи это прямо.""")

    async def test_error_response_keeps_legacy_raw_edit_path(self):
        message = _Message("вопрос")
        deps = self.make_dependencies("ERROR: <bad>&")

        await handle_dialog_delivery(message, **deps)

        self.assertEqual(message.calls, [
            ("answer", "🤖 Анализирую данные...", {}),
            ("edit", "🤖 ERROR: <bad>&", {}),
        ])
        deps["sanitize"].assert_not_called()

    async def test_provider_exception_uses_legacy_error_message(self):
        message = _Message("вопрос")
        deps = self.make_dependencies()
        deps["ask"].side_effect = RuntimeError("fake")

        await handle_dialog_delivery(message, **deps)

        self.assertEqual(message.calls[-1], ("edit", "🤖 Ошибка при обращении к AI-консультанту.", {}))
        deps["logger"].error.assert_called_once_with("handle_dialog_mode: %s", unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
