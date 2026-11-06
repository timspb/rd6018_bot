import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram import Dispatcher

from runtime.production_lifecycle import ProductionRuntimeLifecycle


class ProductionRuntimeLifecycleShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_hook_receives_aiogram_dispatcher_context(self):
        app = SimpleNamespace(
            logger=SimpleNamespace(info=lambda *args: None, warning=lambda *args: None),
            charge_controller=SimpleNamespace(is_active=False),
            hass=SimpleNamespace(close=AsyncMock()),
        )
        lifecycle = ProductionRuntimeLifecycle(app, telegram_runtime=None)
        dispatcher = Dispatcher()
        dispatcher.shutdown.register(lifecycle.on_shutdown)

        with patch("database.close_db", new=AsyncMock()):
            await dispatcher.shutdown.trigger(dispatcher=dispatcher, router=dispatcher)

        app.hass.close.assert_awaited_once()


    async def test_idle_shutdown_never_waits_for_busy_execution_owner(self):
        lock = asyncio.Lock()
        await lock.acquire()
        app = SimpleNamespace(
            logger=SimpleNamespace(info=Mock(), warning=Mock()),
            charge_controller=SimpleNamespace(is_active=False),
            hass=SimpleNamespace(close=AsyncMock()),
        )
        lifecycle = ProductionRuntimeLifecycle(app, None)
        try:
            with patch("runtime.production_lifecycle.get_or_create_execution_port",
                       side_effect=AssertionError("Idle must not acquire owner")):
                with patch("database.close_db", new=AsyncMock()):
                    await asyncio.wait_for(lifecycle.on_shutdown(None), timeout=0.3)
        finally:
            lock.release()
        app.hass.close.assert_awaited_once()

    async def test_busy_active_owner_skips_unsafe_save_but_closes_clients(self):
        lock = asyncio.Lock()
        await lock.acquire()
        controller = SimpleNamespace(is_active=True, _save_session=Mock())
        app = SimpleNamespace(
            logger=SimpleNamespace(info=Mock(), warning=Mock()),
            charge_controller=controller,
            hass=SimpleNamespace(close=AsyncMock()),
        )
        lifecycle = ProductionRuntimeLifecycle(app, None)
        try:
            with patch("runtime.production_lifecycle.get_or_create_execution_port",
                       return_value=SimpleNamespace(_guard_owner_lock=lock)):
                with patch("runtime.production_lifecycle.SHUTDOWN_SESSION_LOCK_TIMEOUT_S", 0.02):
                    with patch("database.close_db", new=AsyncMock()):
                        await asyncio.wait_for(lifecycle.on_shutdown(None), timeout=0.3)
        finally:
            lock.release()
        controller._save_session.assert_not_called()
        app.hass.close.assert_awaited_once()
        app.logger.warning.assert_called()

if __name__ == "__main__":
    unittest.main()
