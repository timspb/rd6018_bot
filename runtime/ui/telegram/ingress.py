"""Registration of the existing free-text Telegram ingress route."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from aiogram import F


def install_text_message_handler(
    router: Any,
    *,
    check_chat: Callable[[Any], Any],
    awaiting_capacity: Mapping[int, str],
    parse_off_command: Callable[[str], Any],
    update_condition: Callable[[Any], bool],
    save_condition: Callable[[], None],
    clear_condition: Callable[[], None],
    set_last_chat: Callable[[int], None],
    get_capacity_handler: Callable[[], Callable[..., Any]],
    get_dialog_handler: Callable[[], Callable[..., Any]],
    parse_mode: Any,
) -> Callable[[Any], Any]:
    """Register the existing dispatch sequence and return its callback."""

    @router.message(F.text & ~F.text.startswith("/"))
    async def text_message_handler(message: Any) -> None:
        if not await check_chat(message):
            return
        user_id = message.from_user.id if message.from_user else 0
        text = (message.text or "").strip()

        # Commands such as /help must not fall through to free-text handling.
        if text.startswith("/"):
            return

        # Preserve the runtime's existing capacity prompt priority over OFF text.
        if not awaiting_capacity.get(user_id):
            off_parsed = parse_off_command(text)
            if off_parsed is not None:
                updated = update_condition(off_parsed)
                save_condition()
                if not updated:
                    await message.answer(
                        "Не удалось принять условие выключения; прежнее условие снято."
                    )
                    return
                condition = ", ".join(off_parsed["parts"])
                await message.answer(
                    f"✅ <b>Выключение по условию:</b> {condition}",
                    parse_mode=parse_mode,
                )
                set_last_chat(message.chat.id)
                return
            if text.strip().lower() == "off":
                clear_condition()
                await message.answer("Сброс условия выключения. Уставки «off» больше не активны.")
                set_last_chat(message.chat.id)
                return

        profile = awaiting_capacity.get(user_id)
        if profile:
            await get_capacity_handler()(message, profile, user_id)
            return

        await get_dialog_handler()(message)

    return text_message_handler


__all__ = ["install_text_message_handler"]
