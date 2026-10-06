"""Telegram transport lifecycle primitives.

The adapter owns construction of the aiogram transport objects.  Handlers remain
in their current module during the staged migration; this module deliberately
does not import runtime, controller, safety, or physical code.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand


logger = logging.getLogger("rd6018.telegram_startup")
_INITIAL_DELAY_S = 1.0
_MAX_DELAY_S = 30.0


class ResilientBootstrapBot(Bot):
    """Aiogram Bot with retry limited to idempotent/bootstrap calls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._rd6018_command_sync_task: asyncio.Task[Any] | None = None

    async def _bootstrap_me_once(self) -> Any:
        return await super().me()

    async def me(self) -> Any:
        delay = _INITIAL_DELAY_S
        attempt = 0
        while True:
            try:
                return await self._bootstrap_me_once()
            except TelegramNetworkError as exc:
                attempt += 1
                logger.warning(
                    "Telegram getMe bootstrap network failure attempt=%d; retry in %.1fs: %s",
                    attempt,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                delay = min(_MAX_DELAY_S, delay * 2.0)

    async def _set_my_commands_once(self, *args: Any, **kwargs: Any) -> Any:
        return await super().set_my_commands(*args, **kwargs)

    async def _deferred_command_sync(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        delay = _INITIAL_DELAY_S
        attempt = 0
        while True:
            try:
                await self._set_my_commands_once(*args, **kwargs)
                logger.info("Deferred Telegram command sync completed")
                return
            except TelegramNetworkError as exc:
                attempt += 1
                logger.warning(
                    "Deferred setMyCommands network failure attempt=%d; retry in %.1fs: %s",
                    attempt,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                delay = min(_MAX_DELAY_S, delay * 2.0)

    async def set_my_commands(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return await self._set_my_commands_once(*args, **kwargs)
        except TelegramNetworkError as exc:
            logger.warning(
                "Telegram setMyCommands bootstrap network failure; deferring sync: %s",
                exc,
            )
            task = self._rd6018_command_sync_task
            if task is None or task.done():
                self._rd6018_command_sync_task = asyncio.create_task(
                    self._deferred_command_sync(tuple(args), dict(kwargs)),
                    name="telegram-command-sync",
                )
            return False


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


async def configure_commands(runtime: TelegramRuntime) -> None:
    """Register the stable operator command surface for the Telegram adapter."""
    await runtime.bot.set_my_commands([
        BotCommand(command="start", description="Открыть дашборд"),
        BotCommand(command="modes", description="Выбрать режим заряда"),
        BotCommand(command="off", description="Условие выключения (preset/команда)"),
        BotCommand(command="logs", description="Последние события"),
        BotCommand(command="ai", description="AI анализ телеметрии"),
        BotCommand(command="stats", description="Где смотреть статистику"),
        BotCommand(command="help", description="Справка по командам"),
        BotCommand(command="entities", description="Статус сущностей HA (RD6018)"),
    ])


def create_telegram_runtime(token: str) -> TelegramRuntime:
    if not token or not str(token).strip():
        raise ValueError("Telegram token is required")
    return TelegramRuntime(
        bot=ResilientBootstrapBot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        ),
        dispatcher=Dispatcher(),
        router=Router(),
    )
