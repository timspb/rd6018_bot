import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe

from telegram.runtime import ResilientBootstrapBot, create_telegram_runtime


TOKEN = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"


def _network_error(message: str = "temporary resolver failure") -> TelegramNetworkError:
    return TelegramNetworkError(method=GetMe(), message=message)


class _TestBot(ResilientBootstrapBot):
    def __init__(self):
        super().__init__(token=TOKEN)
        self.me_calls = 0
        self.command_calls = 0
        self.me_failures = 0
        self.command_failures = 0

    async def _bootstrap_me_once(self):
        self.me_calls += 1
        if self.me_calls <= self.me_failures:
            raise _network_error()
        return {"id": 42}

    async def _set_my_commands_once(self, *args, **kwargs):
        self.command_calls += 1
        if self.command_calls <= self.command_failures:
            raise _network_error()
        return True


class TelegramStartupResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_me_retries_transient_network_failure_with_backoff(self):
        bot = _TestBot()
        bot.me_failures = 2

        sleeper = AsyncMock()
        with patch("telegram.runtime.asyncio.sleep", sleeper):
            result = await bot.me()

        self.assertEqual(result, {"id": 42})
        self.assertEqual(bot.me_calls, 3)
        self.assertEqual([call.args[0] for call in sleeper.await_args_list], [1.0, 2.0])
        await bot.session.close()

    async def test_set_my_commands_defers_after_transient_network_failure(self):
        bot = _TestBot()
        bot.command_failures = 1

        result = await bot.set_my_commands(["start"])
        self.assertFalse(result)

        for _ in range(10):
            if bot.command_calls >= 2:
                break
            await asyncio.sleep(0)

        self.assertEqual(bot.command_calls, 2)
        await bot.session.close()

    async def test_non_network_set_commands_error_is_not_swallowed(self):
        class BadBot(_TestBot):
            async def _set_my_commands_once(self, *args, **kwargs):
                raise RuntimeError("programming/configuration error")

        bot = BadBot()
        with self.assertRaisesRegex(RuntimeError, "programming/configuration error"):
            await bot.set_my_commands([])
        await bot.session.close()

    async def test_factory_returns_resilient_transport_without_composition_patch(self):
        runtime = create_telegram_runtime(TOKEN)
        self.assertIsInstance(runtime.bot, ResilientBootstrapBot)

        from pathlib import Path

        bot_source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("install_telegram_startup_resilience", bot_source)
        self.assertNotIn("telegram_startup_resilience", bot_source)
        await runtime.bot.session.close()


if __name__ == "__main__":
    unittest.main()
