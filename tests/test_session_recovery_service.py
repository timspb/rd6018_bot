import unittest
from pathlib import Path

from application.session_recovery_service import SessionRecoveryService


class FakePort:
    def __init__(self, *, enabled=True):
        self.calls = []
        self.enabled = enabled
        self.fail_on = None
        self.reject = set()

    async def _call(self, name, value=None):
        self.calls.append((name, value) if value is not None else (name,))
        if self.fail_on == name:
            raise RuntimeError(name)
        if name in self.reject:
            return False
        return self.enabled if name == "on" else True

    async def program_voltage(self, value_v):
        return await self._call("voltage", value_v)

    async def program_current(self, value_a):
        return await self._call("current", value_a)

    async def request_verified_off(self):
        return await self._call("off")

    async def request_verified_on(self):
        return await self._call("on")


class SessionRecoveryServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.port = FakePort()
        self.protection_calls = []

        async def protection(v, i):
            self.protection_calls.append(("protection", v, i))

        self.service = SessionRecoveryService(
            self.port, protection, lambda value: min(10.0, value)
        )

    async def test_route_a_success_and_failed_enable(self):
        self.assertTrue(await self.service.reenable_active(14.4, 12.0))
        self.assertEqual(self.protection_calls, [("protection", 14.4, 12.0)])
        self.assertEqual(self.port.calls, [("voltage", 14.4), ("current", 10.0), ("on",)])

        self.port.calls.clear()
        self.port.enabled = False
        self.assertFalse(await self.service.reenable_active(14.4, 12.0))
        self.assertEqual([call[0] for call in self.port.calls], ["voltage", "current", "on"])

    async def test_route_b_safe_wait_and_normal_results(self):
        result = await self.service.restore_idle_link(13.5, 2.0, safe_wait=True)
        self.assertTrue(result.confirmed)
        self.assertFalse(result.output_confirmed)
        self.assertEqual(self.port.calls, [("voltage", 13.5), ("current", 2.0), ("off",)])
        self.port.calls.clear()
        self.port.enabled = True
        result = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        self.assertTrue(result.confirmed)
        self.assertTrue(result.output_confirmed)
        self.assertEqual(self.port.calls, [("voltage", 14.4), ("current", 2.0), ("on",)])

    async def test_route_b_denials_short_circuit_and_retry_without_duplicate_on(self):
        self.port.enabled = False
        first = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        self.assertFalse(first.confirmed)
        self.assertEqual(first.failed_step, "verified_on")
        self.assertEqual([c[0] for c in self.port.calls], ["voltage", "current", "on"])
        self.port.calls.clear()
        self.port.enabled = True
        second = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
        self.assertTrue(second.confirmed)
        self.assertEqual([c[0] for c in self.port.calls], ["voltage", "current", "on"])

        for setter in ("voltage", "current"):
            self.port.calls.clear()
            self.port.reject = {setter}
            result = await self.service.restore_idle_link(14.4, 2.0, safe_wait=False)
            self.assertFalse(result.confirmed)
            self.assertEqual(result.failed_step, setter)
            self.assertNotIn("on", [c[0] for c in self.port.calls])
        self.port.reject.clear()

    async def test_safe_wait_off_denials_are_not_success(self):
        for method in (self.service.restore_idle_link, self.service.restore_output_on):
            self.port.calls.clear()
            self.port.reject = {"off"}
            result = await method(13.5, 2.0, safe_wait=True)
            self.assertFalse(result.confirmed)
            self.assertEqual(result.failed_step, "verified_off")
            self.assertNotIn("on", [c[0] for c in self.port.calls])
            if method == self.service.restore_output_on:
                self.assertEqual([c[0] for c in self.port.calls], ["off"])
        self.port.reject.clear()

    async def test_route_c_normal_never_confirms_prior_output_observation(self):
        result = await self.service.restore_output_on(14.4, 2.0, safe_wait=False)
        self.assertTrue(result.confirmed)
        self.assertIsNone(result.output_confirmed)
        self.assertNotIn("on", [c[0] for c in self.port.calls])

    async def test_route_c_setter_denials_do_not_issue_later_commands(self):
        for setter in ("voltage", "current"):
            with self.subTest(setter=setter):
                self.port.calls.clear()
                self.port.reject = {setter}
                result = await self.service.restore_output_on(14.4, 2.0, safe_wait=False)
                self.assertFalse(result.confirmed)
                self.assertEqual(result.failed_step, setter)
                self.assertNotIn("on", [c[0] for c in self.port.calls])
                self.assertEqual([c[0] for c in self.port.calls],
                                 ["voltage"] if setter == "voltage" else ["voltage", "current"])
        self.port.reject.clear()

    async def test_route_c_safe_wait_setter_denial_stops_after_rejected_setter(self):
        for setter in ("voltage", "current"):
            with self.subTest(setter=setter):
                self.port.calls.clear()
                self.port.reject = {setter}
                result = await self.service.restore_output_on(13.5, 2.0, safe_wait=True)
                self.assertFalse(result.confirmed)
                self.assertEqual(result.failed_step, setter)
                self.assertNotIn("on", [c[0] for c in self.port.calls])
                self.assertEqual([c[0] for c in self.port.calls],
                                 ["off", "voltage"] if setter == "voltage"
                                 else ["off", "voltage", "current"])
        self.port.reject.clear()

    async def test_execution_exceptions_propagate_to_runtime_warning_boundary(self):
        for failed in ("voltage", "current", "off", "on"):
            with self.subTest(failed=failed):
                self.port.calls.clear()
                self.port.fail_on = failed
                with self.assertRaisesRegex(RuntimeError, failed):
                    await self.service.restore_idle_link(
                        13.5 if failed == "off" else 14.4,
                        2.0,
                        safe_wait=failed == "off",
                    )
        self.port.fail_on = None

    async def test_route_c_safe_wait_and_normal_never_request_on(self):
        await self.service.restore_output_on(13.5, 2.0, safe_wait=True)
        self.assertEqual(self.port.calls, [("off",), ("voltage", 13.5), ("current", 2.0)])
        self.port.calls.clear()
        await self.service.restore_output_on(14.4, 2.0, safe_wait=False)
        self.assertEqual(self.port.calls, [("voltage", 14.4), ("current", 2.0)])
        self.assertNotIn("on", [call[0] for call in self.port.calls])

    async def test_setter_and_protection_errors_propagate(self):
        for failed in ("voltage", "current"):
            with self.subTest(failed=failed):
                self.port.calls.clear()
                self.port.fail_on = failed
                with self.assertRaisesRegex(RuntimeError, failed):
                    await self.service.reenable_active(14.4, 2.0)
                self.port.fail_on = None
        self.port.calls.clear()
        self.port.fail_on = "protection"
        async def broken_protection(_v, _i):
            raise RuntimeError("protection")
        broken = SessionRecoveryService(self.port, broken_protection, float)
        with self.assertRaisesRegex(RuntimeError, "protection"):
            await broken.restore_idle_link(14.4, 2.0, safe_wait=False)
        self.assertEqual(self.port.calls, [])

    def test_runtime_delegates_all_recovery_execution_sequences(self):
        source = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        start = source.index("recovery_route = choose_recovery_route(")
        end = source.index("now_ts = time.time()", start)
        recovery = source[start:end]
        self.assertIn("if recovery_route is not RecoveryRoute.NONE:", recovery)
        self.assertIn("recovery_execution = SessionRecoveryService(", recovery)
        self.assertLess(recovery.index("recovery_execution = SessionRecoveryService("),
                        recovery.index("recovery_execution.reenable_active("))
        # The service is not bound at data_logger startup: port identity can
        # change after HA/physical-owner recovery, but authority lock stays app-wide.
        self.assertNotIn("recovery_execution = SessionRecoveryService(",
                         source[source.index("async def data_logger("):start])
        self.assertIn("recovery_execution.reenable_active(", recovery)
        self.assertIn("recovery_execution.restore_idle_link(", recovery)
        self.assertIn("recovery_execution.restore_output_on(", recovery)
        self.assertIn("if not result.confirmed:", recovery)
        self.assertNotIn("charge_controller.stop(", recovery)
        self.assertNotIn("charge_controller._was_unavailable =", recovery)
        self.assertNotIn("clear_session=False", recovery)
        self.assertNotIn("except Exception", recovery)
        denied_b = recovery[recovery.index("if not result.confirmed:"):recovery.index("else:", recovery.index("if not result.confirmed:"))]
        self.assertNotIn('"RESTORE"', denied_b)
        self.assertNotIn("last_checkpoint_time =", denied_b)
        self.assertIn("состояние Output неизвестно", denied_b)
        self.assertNotIn("Заряд остановлен", denied_b)
        denied_c_start = recovery.index("if not result.confirmed:", recovery.index("restore_output_on("))
        denied_c = recovery[denied_c_start:recovery.index("else:", denied_c_start)]
        self.assertNotIn('"RESTORE"', denied_c)
        self.assertNotIn("last_checkpoint_time =", denied_c)
        self.assertIn("состояние Output неизвестно", denied_c)
        self.assertNotIn("Заряд остановлен", denied_c)
        self.assertIn("Output ON отдельно не подтверждался.", recovery)
        self.assertNotIn("await _apply_phase_protection(uv, ui)", recovery)
        self.assertNotIn("program_voltage(uv)", recovery)
        self.assertNotIn("program_current(_cap_current(ui))", recovery)


if __name__ == "__main__":
    unittest.main()
