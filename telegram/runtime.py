"""Telegram transport lifecycle primitives.

The adapter owns construction of the aiogram transport objects.  Handlers remain
in their current module during the staged migration; this module deliberately
does not import runtime, controller, safety, or physical code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


@dataclass(frozen=True)
class TelegramRuntime:
    bot: Bot
    dispatcher: Dispatcher
    router: Router


async def run_polling(
    runtime: TelegramRuntime,
    *,
    shutdown_handler: Callable[[Dispatcher], Awaitable[None]] | None = None,
) -> None:
    """Run the single Telegram polling owner and close its client session.

    Handler registration and domain startup stay outside this transport helper
    during the staged migration.  The helper owns only the transport lifecycle.
    """
    if shutdown_handler is not None:
        runtime.dispatcher.shutdown.register(shutdown_handler)
    try:
        await runtime.dispatcher.start_polling(runtime.bot)
    finally:
        session = getattr(runtime.bot, "session", None)
        if session is not None and not getattr(session, "closed", True):
            await session.close()


def create_telegram_runtime(token: str) -> TelegramRuntime:
    if not token or not str(token).strip():
        raise ValueError("Telegram token is required")
    return TelegramRuntime(
        bot=Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)),
        dispatcher=Dispatcher(),
        router=Router(),
    )
