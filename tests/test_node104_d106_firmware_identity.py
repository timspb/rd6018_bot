"""D106 must pin the currently accepted node104 ESP firmware identity."""
import unittest

from tools.node104_d106_live_observer import (
    EXPECTED_DEVICE_INFO,
    _validate_device_info,
    ro,
)


class D106FirmwareIdentityTests(unittest.TestCase):
    def test_accepts_exact_canonical_node104_identity(self):
        _validate_device_info(dict(EXPECTED_DEVICE_INFO))

    def test_rejects_historical_d091_firmware_default(self):
        actual = dict(EXPECTED_DEVICE_INFO, project_version="2.2-autonomous-authority")
        with self.assertRaisesRegex(ro.ProofError, "firmware identity mismatch"):
            _validate_device_info(actual)

    def test_rejects_each_other_identity_field_mismatch(self):
        for field in ("project_name", "name", "model"):
            actual = dict(EXPECTED_DEVICE_INFO)
            actual[field] = "unexpected"
            with self.subTest(field=field), self.assertRaisesRegex(
                    ro.ProofError, "firmware identity mismatch"):
                _validate_device_info(actual)

    def test_rejects_incomplete_identity(self):
        actual = dict(EXPECTED_DEVICE_INFO)
        del actual["model"]
        with self.assertRaisesRegex(ro.ProofError, "firmware identity mismatch"):
            _validate_device_info(actual)


if __name__ == "__main__":
    unittest.main()