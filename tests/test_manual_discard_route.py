"""Manual interrupted discard remains one fail-closed application boundary."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from manual_mode import ManualSessionState
from manual_runtime import ProductionManualUIRoute


class ManualDiscardRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_discard_requires_interrupted_state(self) -> None:
        manager = SimpleNamespace(state=ManualSessionState.ACTIVE, stop=AsyncMock(return_value=True))
        self.assertFalse(await ProductionManualUIRoute(manager).discard_interrupted())
        manager.stop.assert_not_awaited()

    async def test_interrupted_discard_calls_existing_verified_stop_owner(self) -> None:
        manager = SimpleNamespace(state=ManualSessionState.INTERRUPTED, stop=AsyncMock(return_value=True))
        self.assertTrue(await ProductionManualUIRoute(manager).discard_interrupted())
        manager.stop.assert_awaited_once_with('interrupted_manual_discarded')

    async def test_unconfirmed_off_is_not_reported_as_discard_success(self) -> None:
        manager = SimpleNamespace(state=ManualSessionState.INTERRUPTED, stop=AsyncMock(return_value=False))
        self.assertFalse(await ProductionManualUIRoute(manager).discard_interrupted())
        manager.stop.assert_awaited_once_with('interrupted_manual_discarded')
