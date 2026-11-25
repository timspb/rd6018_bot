"""Read-only free-text AI dialog orchestration and Telegram delivery."""
from __future__ import annotations

from typing import Any, Awaitable, Callable


async def handle_dialog_delivery(
    message: Any,
    *,
    ai_available: bool,
    get_context: Callable[[], Awaitable[str]],
    get_ai_context_dict: Callable[[], Awaitable[dict[str, Any]]],
    get_controller_snapshot: Callable[[], dict[str, Any]],
    get_recent_events: Callable[[int], list[str]],
    ask: Callable[[dict[str, Any]], Awaitable[str]],
    system_prompt: str,
    sanitize: Callable[[str], str],
    parse_mode: Any,
    logger: Any,
) -> None:
    """Prepare and deliver one advisory response using injected read-only providers."""
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
3. Не называй ток "минимальным", если hold-снимок не активен или rule_met = NO.
4. Не делай общих прогнозов и не уходи в рассуждения.
5. Если данных не хватает, скажи это прямо."""
        ai_response = await ask({
            "times": [],
            "voltages": [],
            "currents": [],
            "ai_context": await get_ai_context_dict(),
            "controller_snapshot": get_controller_snapshot(),
            "recent_events": get_recent_events(8),
            "trend_summary": "",
            "user_question": user_question,
            "system_prompt_override": system_prompt,
            "user_prompt_override": user_prompt,
        })

        if ai_response.startswith("ERROR:"):
            await thinking_msg.edit_text(f"🤖 {ai_response}")
        else:
            safe_ai_response = sanitize(ai_response)
            await thinking_msg.edit_text(
                f"🤖 <b>AI-Консультант:</b>\n\n{safe_ai_response}",
                parse_mode=parse_mode,
            )

    except Exception as ex:
        logger.error("handle_dialog_mode: %s", ex)
        await thinking_msg.edit_text("🤖 Ошибка при обращении к AI-консультанту.")


__all__ = ["handle_dialog_delivery"]
