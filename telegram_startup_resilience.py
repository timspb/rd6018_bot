"""V2 Telegram bootstrap resilience for transient network/DNS failures.

The production legacy runtime performs two Telegram API calls before long polling is
fully established: ``setMyCommands`` and aiogram's cached ``bot.me()``/``getMe``.
A short resolver failure at that exact point must not kill an otherwise healthy RD
controller process.

This module deliberately wraps ONLY those bootstrap calls:

* ``bot.me()`` is read-only and aiogram caches the first successful result;
* ``setMyCommands`` is idempotent presentation metadata and may be deferred.

Do not generalize this retry wrapper to arbitrary Telegram send/edit/callback methods:
a transport error after an actuator-related user interaction can be ambiguous and a
blind replay would violate the controller's fail-closed transaction boundaries.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram.exceptions import TelegramNetworkError

logger = logging.getLogger("rd6018.telegram_startup")

_INITIAL_DELAY_S = 1.0
_MAX_DELAY_S = 30.0


def install_telegram_startup_resilience(legacy: Any) -> None:
    """Make Telegram bootstrap survive transient ``TelegramNetworkError`` failures.

    ``set_my_commands`` is attempted once synchronously. On a transient network
    failure it is deferred to a background retry task so the legacy runtime can start
    its local monitor/watchdog tasks immediately. ``bot.me`` retries with capped
    exponential backoff until it succeeds or the task is cancelled; aiogram then
    caches that identity, so normal polling no longer needs a second DNS-dependent
    bootstrap lookup.

    Non-network Telegram exceptions are never swallowed.
    """

    bot = legacy.bot
    if getattr(bot, "_rd6018_startup_resilience_installed", False):
        return

    original_me = bot.me
    original_set_my_commands = bot.set_my_commands
    command_sync_task: asyncio.Task[Any] | None = None

    async def resilient_me(*args: Any, **kwargs: Any) -> Any:
        delay = _INITIAL_DELAY_S
        attempt = 0
        while True:
            try:
                return await original_me(*args, **kwargs)
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

    async def _deferred_command_sync(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        delay = _INITIAL_DELAY_S
        attempt = 0
        while True:
            try:
                await original_set_my_commands(*args, **kwargs)
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

    async def resilient_set_my_commands(*args: Any, **kwargs: Any) -> Any:
        nonlocal command_sync_task
        try:
            return await original_set_my_commands(*args, **kwargs)
        except TelegramNetworkError as exc:
            logger.warning(
                "Telegram setMyCommands bootstrap network failure; deferring sync: %s",
                exc,
            )
            if command_sync_task is None or command_sync_task.done():
                command_sync_task = asyncio.create_task(
                    _deferred_command_sync(tuple(args), dict(kwargs)),
                    name="telegram-command-sync",
                )
            # The legacy main() ignores this result. Returning False keeps the failure
            # explicit to callers without blocking local safety/monitor task startup.
            return False

    bot.me = resilient_me
    bot.set_my_commands = resilient_set_my_commands
    bot._rd6018_startup_resilience_installed = True
