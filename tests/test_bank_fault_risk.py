import time
import unittest

from charge_logic import ChargeController


class DummyHass:
    pass


class BankFaultRiskTests(unittest.TestCase):
    def test_prep_low_start_and_slow_rise_raise_probable(self):
        controller = ChargeController(DummyHass(), notify_cb=lambda _: None)
        controller._stage_tracking_enabled = True
        controller.current_stage = controller.STAGE_PREP

        now = 1_000_000.0
        controller.stage_start_time = now - 2 * 3600
        controller._stage_start_ah = 0.0
        controller._stage_start_voltage = 10.7
        controller._stage_start_current = 0.45
        controller._stage_start_temp = 24.0
        controller._analytics_history.clear()

        risk = controller._bank_fault_risk_snapshot(now, 11.15, 0.32, 25.1, 1.4)

        self.assertIsNotNone(risk)
        self.assertEqual(risk["status"], "high")
        self.assertGreaterEqual(risk["score"], 70)
        self.assertIn("prep_start_low=10.70V", risk["reasons"])
        self.assertTrue(risk["active"])

    def test_main_low_tail_current_stays_watch(self):
        controller = ChargeController(DummyHass(), notify_cb=lambda _: None)
        controller._stage_tracking_enabled = True
        controller.current_stage = controller.STAGE_MAIN

        now = 1_000_000.0
        controller.stage_start_time = now - 24.4 * 3600
        controller._stage_start_ah = 0.0
        controller._stage_start_voltage = 12.8
        controller._stage_start_current = 0.4
        controller._stage_start_temp = 23.0
        controller._analytics_history = [
            (now - 240, 12.76, 0.12, 75.52, 23.0),
            (now - 180, 12.77, 0.12, 75.54, 23.0),
            (now - 120, 12.78, 0.12, 75.58, 24.0),
            (now - 60, 12.80, 0.12, 75.60, 24.0),
        ]

        risk = controller._bank_fault_risk_snapshot(now, 12.80, 0.12, 23.0, 75.60)

        self.assertIsNotNone(risk)
        self.assertEqual(risk["status"], "watch")
        self.assertLess(risk["score"], 50)
        self.assertIn("main_low_current_tail=0.12A", risk["reasons"])


class BankFaultTickTests(unittest.IsolatedAsyncioTestCase):
    async def test_bank_fault_alert_emitted_once(self):
        messages = []
        controller = ChargeController(DummyHass(), notify_cb=messages.append)
        controller._stage_tracking_enabled = True
        controller.current_stage = controller.STAGE_PREP

        now = time.time()
        controller.stage_start_time = now - 2 * 3600
        controller._stage_start_ah = 0.0
        controller._stage_start_voltage = 10.7
        controller._stage_start_current = 0.45
        controller._stage_start_temp = 24.0
        controller._last_hourly_report = now
        controller._last_log_time = now
        controller._last_v_i_history_time = now

        actions = await controller.tick(
            voltage=11.15,
            current=0.32,
            temp_ext=25.1,
            is_cv=True,
            ah=1.4,
            output_is_on=True,
        )

        self.assertIn("notify", actions)
        self.assertIn("Вероятен КЗ банки", actions["notify"])
        self.assertTrue(any("Вероятен КЗ банки" in msg for msg in messages))

        messages.clear()
        await controller.tick(
            voltage=11.14,
            current=0.31,
            temp_ext=25.2,
            is_cv=True,
            ah=1.5,
            output_is_on=True,
        )
        self.assertFalse(any("Вероятен КЗ банки" in msg for msg in messages))


if __name__ == "__main__":
    unittest.main()
