import unittest

from runtime.ui import ChargeView, TransitionView, missing_charge_screen_fields


class V3ChargeScreenSpecTests(unittest.TestCase):
    def test_all_charge_stages_have_required_screen_data(self):
        for stage, phase, waiting in (
            ("PREP", "CC", "12V"), ("MAIN", "CV", "Imin"),
            ("RECOVERY", "CC", "recovery response"), ("MIX", "CC", "Vmax"),
            ("MIX", "CV", "Imin"), ("SAFE_WAIT", "", "safe wait"), ("DONE", "", "complete"),
        ):
            view = ChargeView(
                stage, "AGM 70Ah", phase=phase, targets={"voltage": 14.4, "current": 2.0},
                active_limits={"ovp": 15.0, "ocp": 3.0}, waiting_for=waiting,
                conditions=(TransitionView(waiting, "14.4", 100.0, True),),
            )
            self.assertEqual(missing_charge_screen_fields(view), (), stage)

    def test_missing_screen_contract_is_reported(self):
        self.assertIn("waiting_for", missing_charge_screen_fields(ChargeView("MIX", "manual")))


if __name__ == "__main__":
    unittest.main()
