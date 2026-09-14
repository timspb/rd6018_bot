"""Telegram transport lifecycle primitives.

The adapter owns construction of the aiogram transport objects.  Handlers remain
in their current module during the staged migration; this module deliberately
does not import runtime, controller, safety, or physical code.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


@dataclass(frozen=True)
class TelegramRuntime:
    bot: Bot
    dispatcher: Dispatcher
    router: Router


def create_telegram_runtime(token: str) -> TelegramRuntime:
    if not token or not str(token).strip():
        raise ValueError("Telegram token is required")
    return TelegramRuntime(
        bot=Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)),
        dispatcher=Dispatcher(),
        router=Router(),
    )
