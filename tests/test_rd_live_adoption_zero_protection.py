import unittest

from rd_live_adoption import HandsOffMixObserver


class LiveMixZeroProtectionReadbackTests(unittest.TestCase):
    def test_zero_ocp_is_valid_external_hands_off_fingerprint(self):
        fingerprint = HandsOffMixObserver.fingerprint_from_live(
            {
                "set_voltage": 16.54,
                "set_current": 1.01,
                "ovp": 16.7,
                "ocp": 0.0,
            }
        )

        self.assertIsNotNone(fingerprint)
        assert fingerprint is not None
        self.assertEqual(fingerprint.set_voltage_v, 16.54)
        self.assertEqual(fingerprint.set_current_a, 1.01)
        self.assertEqual(fingerprint.ovp_v, 16.7)
        self.assertEqual(fingerprint.ocp_a, 0.0)

    def test_zero_ovp_and_ocp_are_preserved_as_explicit_external_settings(self):
        fingerprint = HandsOffMixObserver.fingerprint_from_live(
            {
                "set_voltage": 13.8,
                "set_current": 1.0,
                "ovp": 0.0,
                "ocp": 0.0,
            }
        )

        self.assertIsNotNone(fingerprint)
        assert fingerprint is not None
        self.assertEqual(fingerprint.ovp_v, 0.0)
        self.assertEqual(fingerprint.ocp_a, 0.0)

    def test_negative_protection_readback_is_invalid(self):
        self.assertIsNone(
            HandsOffMixObserver.fingerprint_from_live(
                {
                    "set_voltage": 16.54,
                    "set_current": 1.01,
                    "ovp": 16.7,
                    "ocp": -0.1,
                }
            )
        )

    def test_missing_protection_readback_is_still_invalid(self):
        self.assertIsNone(
            HandsOffMixObserver.fingerprint_from_live(
                {
                    "set_voltage": 16.54,
                    "set_current": 1.01,
                    "ovp": 16.7,
                    "ocp": None,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
