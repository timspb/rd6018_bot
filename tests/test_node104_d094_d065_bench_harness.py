from __future__ import annotations

import unittest
from dataclasses import replace

from tools.node104_d094_d065_bench_harness import (
    Action, D065Executor, DisabledLiveGateway, Evidence, HarnessError,
    LiveExecutionDisabled, OfflineNode, verified_off_smoke,
)


class D065OfflineAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = Evidence()

    def test_verified_off_renew_disarm_and_autonomous_enter_exit(self):
        node = OfflineNode()
        driver = D065Executor(node)
        renewed = driver.run(Action.RENEW, self.evidence)
        self.assertTrue(renewed.armed)
        self.assertGreater(renewed.remaining_s, 0)
        self.assertEqual(renewed.generation, 1)
        disarmed = driver.run(Action.DISARM, self.evidence)
        self.assertFalse(disarmed.armed)
        self.assertEqual(disarmed.remaining_s, 0)
        self.assertEqual(disarmed.generation, 1)
        entered = driver.run(Action.ENTER_AUTONOMOUS, self.evidence)
        self.assertTrue(entered.autonomous)
        self.assertFalse(entered.armed)
        exited = driver.run(Action.EXIT_AUTONOMOUS, self.evidence)
        self.assertFalse(exited.autonomous)
        self.assertFalse(exited.armed)  # Exit returns to idle, not old lease.
        self.assertEqual(exited.generation, 3)

    def test_missing_and_failed_ack_are_not_accepted(self):
        for fault in ("missing_ack", "failed_ack"):
            with self.subTest(fault=fault):
                node = OfflineNode(**{fault: True})
                with self.assertRaisesRegex(HarnessError, "acknowledgement"):
                    D065Executor(node).run(Action.RENEW, self.evidence)
                self.assertFalse(node.state.armed)
                self.assertEqual(node.state.remaining_s, 0)

    def test_timeout_and_cancellation_fail_closed_in_simulator(self):
        for fault in ("timeout", "cancelled"):
            with self.subTest(fault=fault):
                node = OfflineNode(**{fault: True})
                with self.assertRaisesRegex(HarnessError, "timeout/cancellation"):
                    D065Executor(node).run(Action.RENEW, self.evidence)
                self.assertFalse(node.state.armed)
                self.assertEqual(node.state.remaining_s, 0)
                self.assertTrue(node.state.tripped)

    def test_stale_ha_or_native_sensor_fails_before_gateway(self):
        for changed in ({"ha_age_s": 9.0}, {"native_age_s": 9.0}):
            node = OfflineNode()
            with self.assertRaisesRegex(HarnessError, "stale"):
                D065Executor(node).run(Action.RENEW, Evidence(**changed))
            self.assertEqual(node.calls, [])

    def test_numberstate_setpoint_is_not_measured_sensor_evidence(self):
        e = Evidence(native_measurement_type="NumberState")
        with self.assertRaisesRegex(HarnessError, "SensorState"):
            verified_off_smoke(e)

    def test_generation_unchanged_is_not_acknowledgement(self):
        node = OfflineNode()
        node.state = Evidence(boot_quarantine=True)
        with self.assertRaisesRegex(HarnessError, "generation progression"):
            D065Executor(node).run(Action.RENEW, self.evidence)
        self.assertFalse(node.state.armed)

    def test_renew_requires_eventual_armed_confirmation(self):
        node = OfflineNode(renew_unconfirmed=True)
        with self.assertRaisesRegex(HarnessError, "armed"):
            D065Executor(node).run(Action.RENEW, self.evidence)
        self.assertFalse(node.state.armed)
        self.assertTrue(node.state.tripped)

    def test_disarm_requires_zero_remaining(self):
        node = OfflineNode(disarm_remaining=True)
        node.state = Evidence(armed=True, remaining_s=100, generation=4)
        with self.assertRaisesRegex(HarnessError, "zero remaining"):
            D065Executor(node).run(Action.DISARM, self.evidence)
        self.assertEqual(node.state.remaining_s, 0)
        self.assertFalse(node.state.armed)
        self.assertTrue(node.state.tripped)

    def test_autonomous_entry_refused_while_managed_lease_armed(self):
        node = OfflineNode()
        node.state = Evidence(armed=True, remaining_s=500, generation=2)
        with self.assertRaisesRegex(HarnessError, "generation progression"):
            D065Executor(node).run(Action.ENTER_AUTONOMOUS, self.evidence)
        self.assertFalse(node.state.autonomous)

    def test_output_on_fault_rolls_back_only_in_simulator(self):
        node = OfflineNode(output_on=True)
        with self.assertRaisesRegex(HarnessError, "Output ON"):
            D065Executor(node).run(Action.RENEW, self.evidence)
        self.assertEqual(node.state.native_r18, 0)
        self.assertFalse(node.state.armed)
        self.assertTrue(node.state.tripped)

    def test_over_ceiling_and_invalid_initial_output_are_rejected(self):
        with self.assertRaisesRegex(HarnessError, "15.5"):
            D065Executor(OfflineNode()).run(
                Action.RENEW, Evidence(setpoint_v=15.51))
        for changed in ({"ha_r18": 1}, {"native_r18": 1},
                        {"native_current": 0.01}, {"ha_voltage": 0.01}):
            with self.subTest(changed=changed):
                with self.assertRaises(HarnessError):
                    verified_off_smoke(Evidence(**changed))

    def test_quarantine_and_trip_fail_closed(self):
        for changed in ({"boot_quarantine": True}, {"tripped": True}):
            node = OfflineNode()
            node.state = Evidence(**changed)
            with self.assertRaises(HarnessError):
                D065Executor(node).run(Action.ENTER_AUTONOMOUS, self.evidence)
            self.assertFalse(node.state.autonomous)

    def test_live_gateway_and_other_gateway_implementations_are_rejected(self):
        with self.assertRaises(LiveExecutionDisabled):
            D065Executor(DisabledLiveGateway())
        with self.assertRaises(LiveExecutionDisabled):
            DisabledLiveGateway().invoke(Action.RENEW, self.evidence)

    def test_nonfinite_negative_age_and_boolean_numeric_proof_denied(self):
        import math
        changes = [
            {"ha_age_s": -0.2}, {"native_age_s": -0.01},
            {"ha_age_s": math.nan}, {"native_age_s": math.inf},
            {"ha_voltage": math.nan}, {"native_current": -math.inf},
            {"ha_r18": False}, {"native_r18": False},
            {"setpoint_v": math.nan}, {"setpoint_v": -1.0},
            {"lease_ttl_s": True}, {"owner_count": True},
            {"handoff_locked": 1}, {"armed": 0}, {"generation": True},
        ]
        for changed in changes:
            with self.subTest(changed=changed):
                node = OfflineNode()
                with self.assertRaises(HarnessError):
                    D065Executor(node).run(Action.RENEW, Evidence(**changed))
                self.assertEqual([], node.calls)

    def test_lease_ttl_and_handoff_ownership_are_invariants(self):
        for changed in ({"lease_ttl_s": 901}, {"owner_count": 2},
                        {"handoff_locked": False}):
            with self.subTest(changed=changed):
                with self.assertRaises(HarnessError):
                    verified_off_smoke(Evidence(**changed))


if __name__ == "__main__":
    unittest.main()
