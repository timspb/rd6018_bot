"""D084: ambiguous recovery must not re-enter the normal charge writer."""
from __future__ import annotations

import ast
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from application.recovery_containment import RecoveryContainment
from application.session_recovery_service import SessionRecoveryService
from runtime.charge.link_session_recovery import RecoveryRoute


class FakePort:
    def __init__(self):
        self.calls: list[str] = []
        self.allow_on = False
        self.allow_off = False

    async def program_voltage(self, value):
        self.calls.append("voltage")
        return True

    async def program_current(self, value):
        self.calls.append("current")
        return True

    async def request_verified_on(self):
        self.calls.append("on")
        return self.allow_on

    async def request_verified_off(self):
        self.calls.append("off")
        return self.allow_off


class RecoveryContainmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.port = FakePort()
        self.phase_calls = []

        async def protect(v, i):
            self.phase_calls.append((v, i))

        self.service = SessionRecoveryService(self.port, protect, float)

    async def test_denial_is_sticky_without_automatic_reset(self):
        hold = RecoveryContainment()
        self.assertFalse(hold.blocked)
        hold = hold.deny(RecoveryRoute.IDLE_LINK, "verified_on")
        self.assertTrue(hold.blocked)
        self.assertEqual(hold.route, RecoveryRoute.IDLE_LINK)
        self.assertEqual(hold.failed_step, "verified_on")
        self.assertIs(hold.deny(RecoveryRoute.IDLE_OUTPUT_ON, "verified_off"), hold)
        with self.assertRaises(FrozenInstanceError):
            hold.route = None
        with self.assertRaises(ValueError):
            RecoveryContainment().deny(RecoveryRoute.NONE, "invalid")

    async def test_lost_link_false_on_blocks_all_later_retries_and_tick(self):
        hold = RecoveryContainment()
        ticks = 0
        for _ in range(4):
            if hold.blocked:
                continue
            result = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
            if not result.confirmed:
                hold = hold.deny(RecoveryRoute.IDLE_LINK, result.failed_step)
                continue
            ticks += 1
        self.assertTrue(hold.blocked)
        self.assertEqual(ticks, 0)
        self.assertEqual(self.port.calls, ["voltage", "current", "on"])

    async def test_failed_safe_wait_off_does_not_abandon_or_replay_output(self):
        hold = RecoveryContainment()
        ticks = 0
        for _ in range(3):
            if hold.blocked:
                continue
            result = await self.service.restore_output_on(13.5, 2.0, safe_wait=True)
            if not result.confirmed:
                hold = hold.deny(RecoveryRoute.IDLE_OUTPUT_ON, result.failed_step)
                continue
            ticks += 1
        self.assertTrue(hold.blocked)
        self.assertEqual(hold.failed_step, "verified_off")
        self.assertEqual(ticks, 0)
        self.assertEqual(self.port.calls, ["off"])
        self.assertNotIn("on", self.port.calls)

    async def test_success_does_not_create_quarantine(self):
        self.port.allow_on = True
        hold = RecoveryContainment()
        result = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        if not result.confirmed:
            hold = hold.deny(RecoveryRoute.IDLE_LINK, result.failed_step)
        self.assertTrue(result.confirmed)
        self.assertFalse(hold.blocked)

    def test_production_gates_before_route_and_tick_under_same_owner(self):
        source = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        logger_start = source.index("async def data_logger()")
        logger_end = source.index("# --- Handlers ---", logger_start)
        block = source[logger_start:logger_end]
        self.assertEqual(block.count("recovery_containment = RecoveryContainment()"), 1)
        self.assertEqual(block.count("recovery_containment = recovery_containment.deny("), 3)
        normal_gate = block.index("if recovery_containment.blocked:")
        route = block.index("recovery_route = choose_recovery_route(")
        post_gate = block.index("if recovery_containment.blocked:", route)
        tick = block.index("await charge_controller.tick(")
        self.assertLess(block.index("if _operator_pause_active():"), normal_gate)
        self.assertLess(normal_gate, route)
        self.assertLess(route, post_gate)
        self.assertLess(post_gate, tick)
        # Normal gate sleeps outside the physical owner lock. After a failed
        # action the second gate continues/unwinds the same lock before tick.
        self.assertIn("await asyncio.sleep(30)\n                continue", block[normal_gate:route])
        self.assertIn("if recovery_containment.blocked:\n                    continue", block[post_gate:tick])
        self.assertIn("async with _runtime_execution_port()._guard_owner_lock:", block[route:tick])
        recovery = block[route:tick]
        self.assertNotIn("charge_controller.stop(", recovery)
        self.assertNotIn("_was_unavailable = False", recovery)
        self.assertNotIn("lease_disarm", recovery)

    def test_latch_module_does_not_touch_hardware_or_logger(self):
        path = Path("application/recovery_containment.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = [node.module for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module]
        self.assertFalse(any(
            name.startswith(("hass", "esphome", "runtime.production",
                             "application.execution_port"))
            for name in modules
        ))
        contents = path.read_text(encoding="utf-8")
        self.assertNotIn("turn_on(", contents)
        self.assertNotIn("turn_off(", contents)


if __name__ == "__main__":
    unittest.main()
