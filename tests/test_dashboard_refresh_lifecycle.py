from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

if not os.environ.get("TG_TOKEN"):
    os.environ["TG_TOKEN"] = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"

from runtime import production_runtime as app


class DashboardRefreshLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        for chat_id in (987654, 987655):
            app.cancel_dashboard_after_60(chat_id)
        await asyncio.sleep(0)

    async def test_navigation_cancels_delayed_refresh(self):
        with patch.object(app, "DASHBOARD_AFTER_MSG_SEC", 0.03), patch.object(
            app, "send_dashboard_to_chat", new=AsyncMock()
        ) as send:
            app.schedule_dashboard_after_60(987654, 42)
            app.cancel_dashboard_after_60(987654)
            await asyncio.sleep(0.06)
        send.assert_not_awaited()

    async def test_only_latest_delayed_refresh_survives_rescheduling(self):
        with patch.object(app, "DASHBOARD_AFTER_MSG_SEC", 0.03), patch.object(
            app, "send_dashboard_to_chat", new=AsyncMock(return_value=101)
        ) as send:
            app.schedule_dashboard_after_60(987655, 42)
            app.schedule_dashboard_after_60(987655, 42)
            await asyncio.sleep(0.06)
        send.assert_awaited_once_with(987655, 42)


if __name__ == "__main__":
    unittest.main()
