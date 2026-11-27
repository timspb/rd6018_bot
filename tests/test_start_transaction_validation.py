import json
import math
import unittest

from application.start_transaction_validation import (
    canonical_candidate_readback_matches,
    native_off_timestamp_after_receipt,
    start_off_receipt_completed_at,
)
from runtime.physical.transports.esp128 import OutputCommandReceipt


class StartTransactionValidationTests(unittest.TestCase):
    def _receipt(self, **overrides):
        values = {
            "request_id": "off-request-1",
            "requested_target": False,
            "terminal_status": "APPLIED",
            "observed_r18": 0,
            "terminal_completed_monotonic": 100.0,
            "connection_generation": 7,
            "raw_terminal_identity": "terminal-1",
        }
        values.update(overrides)
        return OutputCommandReceipt(**values)

    def test_only_exact_typed_off_applied_receipt_yields_completion_time(self):
        self.assertEqual(start_off_receipt_completed_at(
            self._receipt(), receipt_type=OutputCommandReceipt
        ), 100.0)
        self.assertIsNone(start_off_receipt_completed_at(
            None, receipt_type=OutputCommandReceipt
        ))
        self.assertIsNone(start_off_receipt_completed_at(
            self._receipt(requested_target=True), receipt_type=OutputCommandReceipt
        ))
        self.assertIsNone(start_off_receipt_completed_at(
            self._receipt(terminal_status="OUTCOME_UNCERTAIN"), receipt_type=OutputCommandReceipt
        ))
        self.assertIsNone(start_off_receipt_completed_at(
            self._receipt(observed_r18=False), receipt_type=OutputCommandReceipt
        ))
        self.assertIsNone(start_off_receipt_completed_at(
            self._receipt(connection_generation=True), receipt_type=OutputCommandReceipt
        ))
        self.assertIsNone(start_off_receipt_completed_at(
            self._receipt(terminal_completed_monotonic=math.nan), receipt_type=OutputCommandReceipt
        ))

    def test_native_off_requires_fresh_post_receipt_same_generation(self):
        report = (0, {
            "native_type": "SensorState",
            "status": "ok",
            "connection_generation": 7,
            "subscription_timestamp_monotonic": 101.0,
        })
        kwargs = {
            "receipt_completed_monotonic": 100.0,
            "connection_generation": 7,
        }
        self.assertEqual(native_off_timestamp_after_receipt(report, **kwargs), 101.0)
        self.assertIsNone(native_off_timestamp_after_receipt(
            (0, {**report[1], "connection_generation": 6}), **kwargs
        ))
        self.assertIsNone(native_off_timestamp_after_receipt(
            (0, {**report[1], "subscription_timestamp_monotonic": 99.0}), **kwargs
        ))
        self.assertIsNone(native_off_timestamp_after_receipt(
            (0, {**report[1], "status": "stale"}), **kwargs
        ))
        self.assertIsNone(native_off_timestamp_after_receipt(
            (False, report[1]), **kwargs
        ))
        self.assertIsNone(native_off_timestamp_after_receipt(
            (0, {**report[1], "subscription_timestamp_monotonic": True}), **kwargs
        ))

    def test_canonical_candidate_readback_requires_exact_bytes_generation_and_no_pending(self):
        candidate = {"stage": "MAIN", "profile": "EFB"}
        expected = dict(candidate, start_transaction_generation=8)
        raw = json.dumps(expected, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        self.assertTrue(canonical_candidate_readback_matches(
            candidate, generation=8, observed_raw=raw,
            pending_envelope=None, read_error=None,
        ))
        self.assertFalse(canonical_candidate_readback_matches(
            candidate, generation=9, observed_raw=raw,
            pending_envelope=None, read_error=None,
        ))
        self.assertFalse(canonical_candidate_readback_matches(
            candidate, generation=8, observed_raw=raw + b" ",
            pending_envelope=None, read_error=None,
        ))
        self.assertFalse(canonical_candidate_readback_matches(
            candidate, generation=8, observed_raw=raw,
            pending_envelope={"phase": "START_PENDING"}, read_error=None,
        ))
        self.assertFalse(canonical_candidate_readback_matches(
            candidate, generation=8, observed_raw=raw,
            pending_envelope=None, read_error="read_failed",
        ))
        self.assertFalse(canonical_candidate_readback_matches(
            candidate, generation=8, observed_raw=b"{bad",
            pending_envelope=None, read_error=None,
        ))


if __name__ == "__main__":
    unittest.main()
