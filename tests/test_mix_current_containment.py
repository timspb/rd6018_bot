import json
import tempfile
import unittest
from pathlib import Path

from mix_current_containment import (
    MixContainmentError,
    MixContainmentPolicy,
    MixCurrentContainment,
)


class MixCurrentContainmentTests(unittest.TestCase):
    def test_default_policy_has_no_actuator_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = MixCurrentContainment(path=Path(tmp) / "state.json")
            monitor.begin("s1", programmed_ceiling_a=2.16)
            decision = monitor.tighten(
                "s1",
                programmed_ceiling_a=2.16,
                confirmed_imin_a=0.90,
            )
            self.assertFalse(decision.actuator_authority)
            self.assertFalse(decision.changed)
            self.assertEqual(decision.reason, "calibration_required")
            self.assertAlmostEqual(decision.state.ceiling_a, 2.16)

    def test_calibrated_ratchet_can_only_reduce_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = MixCurrentContainment(
                MixContainmentPolicy(containment_headroom_a=0.20),
                Path(tmp) / "state.json",
            )
            monitor.begin("s1", programmed_ceiling_a=2.16)
            first = monitor.tighten(
                "s1", programmed_ceiling_a=2.16, confirmed_imin_a=1.20
            )
            self.assertAlmostEqual(first.state.ceiling_a, 1.40)
            second = monitor.tighten(
                "s1", programmed_ceiling_a=3.00, confirmed_imin_a=1.50
            )
            self.assertAlmostEqual(second.state.ceiling_a, 1.40)
            self.assertFalse(second.changed)
            third = monitor.tighten(
                "s1", programmed_ceiling_a=2.16, confirmed_imin_a=0.90
            )
            self.assertAlmostEqual(third.state.ceiling_a, 1.10)

    def test_programmed_current_below_candidate_remains_hard_upper_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = MixCurrentContainment(
                MixContainmentPolicy(containment_headroom_a=0.50),
                Path(tmp) / "state.json",
            )
            monitor.begin("s1", programmed_ceiling_a=1.00)
            decision = monitor.tighten(
                "s1", programmed_ceiling_a=0.80, confirmed_imin_a=0.70
            )
            self.assertAlmostEqual(decision.state.ceiling_a, 0.80)

    def test_tighter_ceiling_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            first = MixCurrentContainment(
                MixContainmentPolicy(containment_headroom_a=0.20), path
            )
            first.begin("s1", programmed_ceiling_a=2.00)
            first.tighten("s1", programmed_ceiling_a=2.00, confirmed_imin_a=0.80)

            second = MixCurrentContainment(
                MixContainmentPolicy(containment_headroom_a=0.20), path
            )
            restored = second.load("s1")
            self.assertAlmostEqual(restored.ceiling_a, 1.00)
            decision = second.tighten(
                "s1", programmed_ceiling_a=2.50, confirmed_imin_a=1.50
            )
            self.assertAlmostEqual(decision.state.ceiling_a, 1.00)

    def test_corrupt_persistence_that_enlarges_authority_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "session_id": "s1",
                        "ceiling_a": 3.0,
                        "initial_programmed_ceiling_a": 2.0,
                        "signal_censored": False,
                    }
                ),
                encoding="utf-8",
            )
            monitor = MixCurrentContainment(path=path)
            with self.assertRaisesRegex(MixContainmentError, "enlarged"):
                monitor.load("s1")

    def test_ceiling_reached_is_explicit_censored_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = MixCurrentContainment(path=Path(tmp) / "state.json")
            monitor.begin("s1", programmed_ceiling_a=2.0)
            state = monitor.mark_current_ceiling_reached("s1")
            self.assertTrue(state.signal_censored)
            self.assertAlmostEqual(state.ceiling_a, 2.0)

    def test_invalid_or_zero_calibration_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = MixCurrentContainment(
                MixContainmentPolicy(containment_headroom_a=0.0),
                Path(tmp) / "state.json",
            )
            monitor.begin("s1", programmed_ceiling_a=2.0)
            with self.assertRaises(MixContainmentError):
                monitor.tighten("s1", programmed_ceiling_a=2.0, confirmed_imin_a=1.0)


if __name__ == "__main__":
    unittest.main()
