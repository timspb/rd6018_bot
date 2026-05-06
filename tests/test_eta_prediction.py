import unittest

from charge_logic import ChargeController


class DummyHass:
    pass


class EtaPredictionTests(unittest.TestCase):
    def test_prep_prediction_is_hours_not_fallback(self):
        controller = ChargeController(DummyHass(), notify_cb=lambda _: None)
        controller._stage_tracking_enabled = True
        controller.current_stage = controller.STAGE_PREP
        now = 1_000_000.0
        controller.stage_start_time = now - 8 * 3600
        controller._stage_start_voltage = 11.20
        controller._stage_start_current = 0.70
        controller._stage_start_temp = 23.0
        controller._analytics_history.clear()
        controller._analytics_history.extend(
            [
                (now - 15 * 60, 11.55, 0.69, 4.8, 23.0),
                (now - 10 * 60, 11.58, 0.69, 5.0, 23.0),
                (now - 5 * 60, 11.62, 0.68, 5.1, 23.1),
                (now, 11.68, 0.68, 5.2, 23.1),
            ]
        )

        predicted, _, _ = controller.predict_finish(11.68, 0.68, 5.2, 23.1)

        self.assertNotEqual(predicted, "~5–10 мин")
        self.assertTrue("ч" in predicted or "м" in predicted)

    def test_main_cv_prediction_reflects_hold_tail(self):
        controller = ChargeController(DummyHass(), notify_cb=lambda _: None)
        controller._stage_tracking_enabled = True
        controller.current_stage = controller.STAGE_MAIN
        controller.battery_type = controller.PROFILE_CA
        controller.stage_start_time = 1_000_000.0 - 5 * 3600
        controller._stage_start_voltage = 13.20
        controller._stage_start_current = 5.00
        controller._stage_start_temp = 23.0
        controller._cv_since = 1_000_000.0 - 45 * 60
        controller._first_stage_hold_since = 1_000_000.0 - 30 * 60
        controller._first_stage_hold_current = 0.28
        controller._analytics_history.clear()
        controller._analytics_history.extend(
            [
                (1_000_000.0 - 20 * 60, 14.45, 0.34, 7.8, 23.0),
                (1_000_000.0 - 15 * 60, 14.50, 0.31, 7.9, 23.1),
                (1_000_000.0 - 10 * 60, 14.54, 0.29, 8.0, 23.1),
                (1_000_000.0 - 5 * 60, 14.57, 0.27, 8.1, 23.2),
                (1_000_000.0, 14.60, 0.26, 8.2, 23.2),
            ]
        )

        predicted, _, _ = controller.predict_finish(14.60, 0.26, 8.2, 23.2)

        self.assertNotEqual(predicted, "~5–10 мин")
        self.assertTrue("ч" in predicted or "м" in predicted)


if __name__ == "__main__":
    unittest.main()
