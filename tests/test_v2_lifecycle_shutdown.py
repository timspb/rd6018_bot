import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Dispatcher

from runtime.v2_lifecycle import V2RuntimeLifecycle


class V2RuntimeLifecycleShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_hook_receives_aiogram_dispatcher_context(self):
        app = SimpleNamespace(
            logger=SimpleNamespace(info=lambda *args: None, warning=lambda *args: None),
            charge_controller=SimpleNamespace(is_active=False),
            hass=SimpleNamespace(close=AsyncMock()),
        )
        lifecycle = V2RuntimeLifecycle(app, telegram_runtime=None)
        dispatcher = Dispatcher()
        dispatcher.shutdown.register(lifecycle.on_shutdown)

        with patch("database.close_db", new=AsyncMock()):
            await dispatcher.shutdown.trigger(dispatcher=dispatcher, router=dispatcher)

        app.hass.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
