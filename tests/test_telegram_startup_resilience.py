import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe

from telegram_startup_resilience import install_telegram_startup_resilience


def _network_error(message: str = "temporary resolver failure") -> TelegramNetworkError:
    return TelegramNetworkError(method=GetMe(), message=message)


class _Legacy:
    def __init__(self, bot):
        self.bot = bot


class TelegramStartupResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_me_retries_transient_network_failure_with_backoff(self):
        class Bot:
            def __init__(self):
                self.calls = 0

            async def me(self):
                self.calls += 1
                if self.calls < 3:
                    raise _network_error()
                return {"id": 42}

            async def set_my_commands(self, *args, **kwargs):
                return True

        bot = Bot()
        install_telegram_startup_resilience(_Legacy(bot))

        sleeper = AsyncMock()
        with patch("telegram_startup_resilience.asyncio.sleep", sleeper):
            result = await bot.me()

        self.assertEqual(result, {"id": 42})
        self.assertEqual(bot.calls, 3)
        self.assertEqual([call.args[0] for call in sleeper.await_args_list], [1.0, 2.0])

    async def test_set_my_commands_defers_after_transient_network_failure(self):
        class Bot:
            def __init__(self):
                self.calls = 0

            async def me(self):
                return {"id": 42}

            async def set_my_commands(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise _network_error()
                return True

        bot = Bot()
        install_telegram_startup_resilience(_Legacy(bot))

        result = await bot.set_my_commands(["start"])
        self.assertFalse(result)

        # The deferred task retries immediately once before any backoff is needed.
        for _ in range(10):
            if bot.calls >= 2:
                break
            await asyncio.sleep(0)

        self.assertEqual(bot.calls, 2)

    async def test_non_network_set_commands_error_is_not_swallowed(self):
        class Bot:
            async def me(self):
                return {"id": 42}

            async def set_my_commands(self, *args, **kwargs):
                raise RuntimeError("programming/configuration error")

        bot = Bot()
        install_telegram_startup_resilience(_Legacy(bot))

        with self.assertRaisesRegex(RuntimeError, "programming/configuration error"):
            await bot.set_my_commands([])

    async def test_install_is_idempotent(self):
        class Bot:
            def __init__(self):
                self.me_calls = 0

            async def me(self):
                self.me_calls += 1
                return {"id": 42}

            async def set_my_commands(self, *args, **kwargs):
                return True

        bot = Bot()
        legacy = _Legacy(bot)
        install_telegram_startup_resilience(legacy)
        first_me = bot.me
        first_set = bot.set_my_commands
        install_telegram_startup_resilience(legacy)

        self.assertIs(bot.me, first_me)
        self.assertIs(bot.set_my_commands, first_set)
        await bot.me()
        self.assertEqual(bot.me_calls, 1)


if __name__ == "__main__":
    unittest.main()
