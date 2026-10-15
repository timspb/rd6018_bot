"""D070b in-process owner lock, isolated fake tasks; never actual hardware."""
import asyncio
import unittest

from application.execution_port import ExecutionPort
from application.guard_execution_owner_lock import GuardExecutionOwnerLock


class GuardOwnerLockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lock = GuardExecutionOwnerLock()

    async def test_reentry_same_task_does_not_deadlock(self):
        seen = []
        async with self.lock:
            seen.append("outer")
            async with self.lock:
                seen.append("inner")
                self.assertEqual(self.lock.depth, 2)
                self.assertTrue(self.lock.locked())
            self.assertEqual(self.lock.depth, 1)
            self.assertTrue(self.lock.locked())
        self.assertFalse(self.lock.locked())
        self.assertIsNone(self.lock.owner_task)
        self.assertEqual(seen, ["outer", "inner"])

    async def test_separate_task_cannot_interleave_owner_commands(self):
        order = []
        gate = asyncio.Event()
        entered = asyncio.Event()

        async def first():
            async with self.lock:
                order.append("first_start")
                entered.set()
                await gate.wait()
                order.append("first_end")

        async def second():
            async with self.lock:
                order.append("second_start")
                await asyncio.sleep(0)
                order.append("second_end")

        one = asyncio.create_task(first())
        await asyncio.wait_for(entered.wait(), 1)
        two = asyncio.create_task(second())
        await asyncio.sleep(0)
        self.assertEqual(order, ["first_start"])
        self.assertFalse(two.done())
        gate.set()
        await asyncio.wait_for(asyncio.gather(one, two), 1)
        self.assertEqual(order, [
            "first_start", "first_end", "second_start", "second_end",
        ])

    async def test_cancelled_waiter_never_releases_actual_owner(self):
        async with self.lock:
            waiter = asyncio.create_task(self.lock.acquire())
            await asyncio.sleep(0)
            waiter.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            self.assertTrue(self.lock.locked())
            self.assertEqual(self.lock.depth, 1)
            self.assertIs(self.lock.owner_task, asyncio.current_task())
        self.assertFalse(self.lock.locked())

    async def test_owner_cancellation_unwinds_lock(self):
        entered = asyncio.Event()

        async def interrupted():
            async with self.lock:
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(interrupted())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.lock.depth, 0)
        self.assertFalse(self.lock.locked())
        async with self.lock:
            self.assertEqual(self.lock.depth, 1)

    async def test_exception_in_nested_transaction_releases_all_depth(self):
        async def failure():
            async with self.lock:
                raise ValueError("synthetic hardware failure")

        with self.assertRaises(ValueError):
            await self.lock.run(failure)
        self.assertEqual(self.lock.depth, 0)
        self.assertFalse(self.lock.locked())

    async def test_foreign_task_cannot_release_current_owner(self):
        async with self.lock:
            async def foreign_release():
                with self.assertRaises(RuntimeError):
                    self.lock.release()
            await asyncio.create_task(foreign_release())
            self.assertEqual(self.lock.depth, 1)

    async def test_execution_port_accepts_exact_bound_task_lock_only(self):
        class Owner:
            pass
        port = ExecutionPort(Owner())
        port.bind_guard_owner_lock(self.lock)
        self.assertIs(port._guard_owner_lock, self.lock)
        port.bind_guard_owner_lock(self.lock)
        with self.assertRaises(RuntimeError):
            port.bind_guard_owner_lock(GuardExecutionOwnerLock())
        with self.assertRaises(RuntimeError):
            port.bind_guard_owner_lock(asyncio.Lock())

    async def test_execution_port_serializes_nested_setters_and_allows_emergency_off(self):
        events = []
        entered = asyncio.Event()
        release = asyncio.Event()

        class Owner:
            async def set_current(self, value):
                events.append(("current_start", value))
                entered.set()
                await release.wait()
                events.append(("current_end", value))
                return True
            async def set_voltage(self, value):
                events.append(("voltage", value))
                return True
            async def turn_off(self):
                events.append(("OFF", None))
                return True

        port = ExecutionPort(Owner())
        port.bind_guard_owner_lock(self.lock)
        first = asyncio.create_task(port.apply_current_with_ocp(
            target_current_a=2.0, current_set_a=1.0, target_ocp_a=None,
            max_stage_current_a=12.0, ocp_offset_a=1.0, has_ocp=False,
            stabilize_delay_s=0,
        ))
        await asyncio.wait_for(entered.wait(), 1)
        second = asyncio.create_task(port.program_voltage(14.4))
        await asyncio.sleep(0)
        self.assertEqual(events, [("current_start", 2.0)])
        await port.request_verified_off()
        self.assertEqual(events[-1], ("OFF", None))
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 1)
        self.assertEqual(events[1:], [("OFF", None), ("current_end", 2.0), ("voltage", 14.4)])

    async def test_production_factory_reuses_one_app_port_and_lock(self):
        from application.execution_port import get_or_create_execution_port
        class App:
            hass = object()
        app = App()
        port = get_or_create_execution_port(app)
        lock = app.guard_execution_owner_lock
        self.assertIs(get_or_create_execution_port(app), port)
        self.assertIs(app.guard_execution_owner_lock, lock)
        self.assertIs(port._guard_owner_lock, lock)

    async def test_emergency_off_does_not_depend_on_owner_waiters(self):
        """Prove architecture contract with fake OFF, not a hardware watchdog."""
        called = []
        async with self.lock:
            normal = asyncio.create_task(self.lock.run(
                lambda: self._append(called, "normal")
            ))
            await asyncio.sleep(0)
            # Separate emergency path deliberately does not acquire this
            # potentially busy application lock.
            await self._append(called, "emergency_OFF")
            self.assertEqual(called, ["emergency_OFF"])
            normal.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await normal
        self.assertFalse(self.lock.locked())

    @staticmethod
    async def _append(events, name):
        events.append(name)


if __name__ == "__main__":
    unittest.main()
