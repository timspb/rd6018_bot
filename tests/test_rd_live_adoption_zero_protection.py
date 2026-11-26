import unittest

from rd_live_adoption import HandsOffMixObserver


class LiveMixVIOnlyFingerprintTests(unittest.TestCase):
    def test_external_fingerprint_uses_only_programmed_voltage_and_current(self):
        fingerprint = HandsOffMixObserver.fingerprint_from_live(
            {"set_voltage": 16.54, "set_current": 1.01}
        )
        self.assertIsNotNone(fingerprint)
        self.assertEqual(fingerprint.set_voltage_v, 16.54)
        self.assertEqual(fingerprint.set_current_a, 1.01)
        self.assertFalse(hasattr(fingerprint, "ovp_v"))
        self.assertFalse(hasattr(fingerprint, "ocp_a"))

    def test_retired_protection_values_cannot_change_fingerprint(self):
        baseline = HandsOffMixObserver.fingerprint_from_live(
            {"set_voltage": 13.8, "set_current": 1.0}
        )
        for retired in ({"ovp": 0.0, "ocp": 0.0},
                        {"ovp": None, "ocp": None},
                        {"ovp": 16.7, "ocp": -0.1}):
            with self.subTest(retired=retired):
                candidate = HandsOffMixObserver.fingerprint_from_live(
                    {"set_voltage": 13.8, "set_current": 1.0, **retired}
                )
                self.assertEqual(candidate, baseline)

    def test_invalid_voltage_or_current_blocks_adoption_fingerprint(self):
        for key, bad in (("set_voltage", None), ("set_current", None),
                         ("set_voltage", -1.0), ("set_current", -1.0)):
            with self.subTest(key=key, bad=bad):
                live = {"set_voltage": 16.54, "set_current": 1.01}
                live[key] = bad
                self.assertIsNone(HandsOffMixObserver.fingerprint_from_live(live))


if __name__ == "__main__":
    unittest.main()
