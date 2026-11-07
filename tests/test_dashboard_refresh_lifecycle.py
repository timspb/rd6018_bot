"""Obsolete deferred dashboard publisher must not re-enter production."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DashboardRefreshLifecycleTests(unittest.TestCase):
    def test_no_legacy_delayed_graph_or_text_publishers(self):
        source = (ROOT / "runtime/production_runtime.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        functions = {
            item.name for item in module.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for forbidden in (
            "send_dashboard_to_chat",
            "schedule_dashboard_after_60",
            "_delayed_dashboard_task",
            "cancel_dashboard_after_60",
            "dashboard_lifecycle_lock",
        ):
            self.assertNotIn(forbidden, functions)
        self.assertNotIn("schedule_dashboard_after_60(", source)

    def test_only_one_owner_for_timed_graph_refresh(self):
        source = (ROOT / "operator_dashboard.py").read_text(encoding="utf-8")
        self.assertIn("owner.start_graph_refresh(refresh_graph_message)", source)
        self.assertNotIn("async def graph_refresh_loop(", source)
        self.assertNotIn("ensure_graph_refresh_loop", source)
        owner = (ROOT / "runtime/ui/telegram/panel_lifecycle.py").read_text(encoding="utf-8")
        self.assertIn("async with self._locks[chat_id]", owner)
        self.assertIn("async def publish_last(", owner)
        self.assertIn("async def refresh_graph(", owner)
        self.assertIn("async def _graph_tick_loop(", owner)
        self.assertIn("await self.refresh_graph(", owner)


if __name__ == "__main__":
    unittest.main()
