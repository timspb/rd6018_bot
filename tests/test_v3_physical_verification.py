import unittest

from runtime.output.bridge import HardwareSnapshot
from runtime.physical.verification import PhysicalStateComparator, PhysicalVerificationService, VerificationResult


class PhysicalVerificationTests(unittest.TestCase):
    def setUp(self):
        self.comparator = PhysicalStateComparator(
            voltage_tolerance=.01, current_tolerance=.05, protection_tolerance=.05,
            timestamp_tolerance=10, clock=lambda: 100,
        )
        self.service = PhysicalVerificationService(self.comparator)

    def snapshot(self, **changes):
        values = dict(timestamp=100, connection_state="connected", output_state=False,
                      measured_voltage=0, measured_current=0, configured_voltage=13.94,
                      configured_current=.55, ovp=16.7, ocp=12, temperature=31)
        values.update(changes)
        return HardwareSnapshot(**values)

    def test_pre_and_post_match(self):
        expected = self.snapshot()
        pre = self.service.verify_pre_action(expected, self.snapshot(), transport="ha102",
                                             require_fields=("output_state", "measured_current"))
        post = self.service.verify_post_action("disable_output", expected, self.snapshot(),
                                              require_fields=("output_state", "measured_current"))
        self.assertEqual(pre.result, VerificationResult.MATCH)
        self.assertEqual(post.result, VerificationResult.MATCH)
        evidence = self.service.build_evidence(before_snapshot=expected, requested_state=expected,
                                               write_result="sent", pre_readback=expected,
                                               pre_comparison=pre, action="disable_output",
                                               post_readback=expected, post_comparison=post)
        self.assertEqual(evidence.final_result, VerificationResult.MATCH)

    def test_mismatch_and_stale_fail_closed(self):
        expected = self.snapshot()
        mismatch = self.service.verify_post_action("disable_output", expected,
                                                   self.snapshot(measured_current=.2), require_fields=("measured_current",))
        stale = self.service.verify_post_action("disable_output", expected,
                                                self.snapshot(timestamp=80), require_fields=("output_state",))
        self.assertEqual(mismatch.result, VerificationResult.MISMATCH)
        self.assertIn("measured_current", mismatch.differences)
        self.assertEqual(stale.result, VerificationResult.MISMATCH)
        self.assertIn("timestamp_stale", stale.differences)

    def test_missing_readback_is_failed(self):
        expected = self.snapshot()
        observed = self.snapshot(measured_current=None)
        result = self.service.verify_post_action("disable_output", expected, observed,
                                                 require_fields=("measured_current",))
        self.assertEqual(result.result, VerificationResult.MISMATCH)
        self.assertIn("missing:measured_current", result.differences)
