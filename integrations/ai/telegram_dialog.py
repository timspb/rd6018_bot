"""Optional AI dialog response preparation and Telegram presentation."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

async def handle_dialog_delivery(
    message: Any,
    *,
    ai_available: bool,
    get_context: Callable[[], Awaitable[str]],
    ask: Callable[[dict[str, str]], Awaitable[str]],
    system_prompt: str,
    sanitize: Callable[[str], str],
    parse_mode: Any,
    logger: Any,
) -> None:
    """Deliver the legacy free-text AI reply using existing runtime dependencies."""
    if not ai_available:
        await message.answer("🤖 AI-консультант недоступен (не настроен API ключ)")
        return

    user_question = (message.text or "").strip()
    if not user_question:
        return

    thinking_msg = await message.answer("🤖 Анализирую данные...")
    try:
        context = await get_context()
        user_prompt = f"""=== ПОЛНЫЙ СЛЕПОК RD6018 ===
{context}

=== ВОПРОС ПОЛЬЗОВАТЕЛЯ ===
{user_question}

=== КАК ОТВЕЧАТЬ ===
1. Сначала дай прямой ответ на вопрос.
2. Если вопрос про текущий этап, время на минимальном токе или переход, используй только факты из контекста, hold-снимка и таймеров.
3. Не называй ток \"минимальным\", если hold-снимок не активен или rule_met = NO.
4. Не делай общих прогнозов и не уходи в рассуждения.
5. Если данных не хватает, скажи это прямо."""
        ai_response = await ask({
            "system_prompt_override": system_prompt,
            "user_prompt_override": user_prompt,
        })
        if ai_response.startswith("ERROR:"):
            await thinking_msg.edit_text(sanitize(f"🤖 {ai_response}"), parse_mode=parse_mode)
        else:
            safe_response = sanitize(ai_response)
            await thinking_msg.edit_text(
                f"🤖 <b>AI-Консультант:</b>\r\n\r\n{safe_response}",
                parse_mode=parse_mode,
            )
    except Exception:
        # Exception strings from HTTP clients can contain request credentials.
        logger.error("handle_dialog_mode: AI request failed")
        await thinking_msg.edit_text(
            sanitize("🤖 Ошибка при обращении к AI-консультанту."),
            parse_mode=parse_mode,
        )
