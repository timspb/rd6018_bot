import ast
import types
import unittest
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def _load_uptime_sync_symbols():
    source = BOT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(BOT_PATH))

    wanted_assigns = {"UPTIME_AS_CHARGE_TIMER_MAX_SEC", "UPTIME_SYNC_MAX_DRIFT_SEC"}
    wanted_funcs = {
        "_parse_uptime_to_elapsed_sec",
        "_sync_total_start_from_uptime",
        "_apply_restore_time_corrections",
    }

    selected_nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id in wanted_assigns for t in node.targets):
                selected_nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_funcs:
            selected_nodes.append(node)

    module_ast = ast.Module(body=selected_nodes, type_ignores=[])
    code = compile(module_ast, filename=str(BOT_PATH), mode="exec")

    ns = {
        "time": __import__("time"),
        "datetime": datetime,
        "Optional": Optional,
        "Dict": Dict,
    }
    exec(code, ns)
    return ns


class _FakeController:
    def __init__(self, *, is_active=True, total_start_time=0.0, stage_start_time=0.0, link_lost_at=0.0):
        self.is_active = is_active
        self.total_start_time = total_start_time
        self.stage_start_time = stage_start_time
        self._link_lost_at = link_lost_at


class UptimeSyncTests(unittest.TestCase):
    def setUp(self):
        self.ns = _load_uptime_sync_symbols()
        self.fixed_now = 1_000_000.0
        self.ns["time"] = types.SimpleNamespace(time=lambda: self.fixed_now)

    def test_sync_updates_when_drift_within_limit(self):
        sync = self.ns["_sync_total_start_from_uptime"]
        controller = _FakeController(is_active=True, total_start_time=self.fixed_now - 1200)

        changed = sync(
            controller,
            {"uptime": 1220},
            max_drift_sec=300,
            allow_init=False,
        )

        self.assertTrue(changed)
        self.assertAlmostEqual(controller.total_start_time, self.fixed_now - 1220)

    def test_sync_rejects_when_drift_too_large(self):
        sync = self.ns["_sync_total_start_from_uptime"]
        controller = _FakeController(is_active=True, total_start_time=self.fixed_now - 1200)

        changed = sync(
            controller,
            {"uptime": 1700},
            max_drift_sec=300,
            allow_init=False,
        )

        self.assertFalse(changed)
        self.assertAlmostEqual(controller.total_start_time, self.fixed_now - 1200)

    def test_sync_does_not_init_when_allow_init_false(self):
        sync = self.ns["_sync_total_start_from_uptime"]
        controller = _FakeController(is_active=True, total_start_time=0.0)

        changed = sync(
            controller,
            {"uptime": 300},
            max_drift_sec=300,
            allow_init=False,
        )

        self.assertFalse(changed)
        self.assertEqual(controller.total_start_time, 0.0)

    def test_apply_restore_shifts_timers_and_syncs_if_close(self):
        apply_restore = self.ns["_apply_restore_time_corrections"]
        controller = _FakeController(
            is_active=True,
            total_start_time=self.fixed_now - 3600,
            stage_start_time=self.fixed_now - 900,
            link_lost_at=self.fixed_now - 60,
        )

        apply_restore(controller, {"uptime": 3650})

        self.assertEqual(controller._link_lost_at, 0)
        self.assertAlmostEqual(controller.stage_start_time, self.fixed_now - 840)
        self.assertAlmostEqual(controller.total_start_time, self.fixed_now - 3650)

    def test_apply_restore_does_not_overwrite_with_far_uptime(self):
        apply_restore = self.ns["_apply_restore_time_corrections"]
        controller = _FakeController(
            is_active=True,
            total_start_time=self.fixed_now - 3600,
            stage_start_time=self.fixed_now - 900,
            link_lost_at=self.fixed_now - 60,
        )

        apply_restore(controller, {"uptime": 10})

        self.assertEqual(controller._link_lost_at, 0)
        self.assertAlmostEqual(controller.total_start_time, self.fixed_now - 3540)
        self.assertAlmostEqual(controller.stage_start_time, self.fixed_now - 840)


if __name__ == "__main__":
    unittest.main()
