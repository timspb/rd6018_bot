import unittest

from runtime.telemetry.source import observe_data_logger_cycle


class DataLoggerObservationTests(unittest.TestCase):
    def test_projection_matches_legacy_key_and_format_semantics(self):
        live = {
            "battery_voltage": "12.34", "voltage": "12.56", "current": "1.25",
            "power": "15.7", "temp_ext": "21.5", "ah": "0.7",
            "is_cv": "true", "is_cc": 1, "switch": "ON", "battery_mode": "on",
            "input_voltage": "230", "temp_int": "44", "set_voltage": "14.4",
            "set_current": "5", "protection_code": 3,
        }
        observed = observe_data_logger_cycle(live)
        self.assertEqual(observed.battery_voltage_v, 12.34)
        self.assertEqual(observed.output_voltage_v, 12.56)
        self.assertEqual(observed.current_a, 1.25)
        self.assertEqual(observed.power_w, 15.7)
        self.assertEqual(observed.external_temperature_raw, "21.5")
        self.assertEqual(observed.external_temperature_c, 21.5)
        self.assertEqual(observed.amp_hours, 0.7)
        self.assertTrue(observed.is_cv)
        self.assertTrue(observed.is_cc)
        self.assertEqual(observed.output_switch, "ON")
        self.assertTrue(observed.output_on)
        self.assertTrue(observed.battery_mode_on)
        self.assertEqual(observed.input_voltage_v, 230.0)
        self.assertEqual(observed.internal_temperature_c, 44.0)
        self.assertEqual(observed.set_voltage_v, 14.4)
        self.assertEqual(observed.set_current_a, 5.0)
        self.assertEqual(observed.live_context, "📊 Факт: V 12.34В | I 1.25А | T 21.5°C | режим CV")
        self.assertFalse(hasattr(observed, "protection_code"))

    def test_missing_unknown_and_noncanonical_output_keep_previous_behavior(self):
        live = {
            "voltage": "15", "temp_ext": "unavailable", "is_cv": "yes",
            "is_cc": True, "switch": True, "set_voltage": "0", "set_current": "-1",
        }
        observed = observe_data_logger_cycle(
            live, manual_active=True, manual_mode_label="Ручной",
        )
        self.assertEqual(observed.battery_voltage_v, 0.0)
        self.assertEqual(observed.output_voltage_v, 15.0)
        self.assertEqual(observed.external_temperature_raw, "unavailable")
        self.assertEqual(observed.external_temperature_c, 0.0)
        self.assertTrue(observed.is_cv)
        self.assertTrue(observed.is_cc)
        self.assertIs(observed.output_switch, True)
        self.assertFalse(observed.output_on)
        self.assertEqual(observed.set_voltage_v, 0.0)
        self.assertEqual(observed.set_current_a, -1.0)
        self.assertEqual(observed.live_context, "📊 Факт: V 0.00В | I 0.00А | T 0.0°C | режим Ручной")

    def test_manual_mode_label_keeps_empty_and_none_values(self):
        empty = observe_data_logger_cycle({}, manual_active=True, manual_mode_label="")
        none = observe_data_logger_cycle({}, manual_active=True, manual_mode_label=None)
        self.assertIn("| режим ", empty.live_context)
        self.assertIn("| режим None", none.live_context)

    def test_unknown_output_switch_stays_unknown_for_runtime_mirror_dispatch(self):
        observed = observe_data_logger_cycle({"switch": "unknown"})
        self.assertEqual(observed.output_switch, "unknown")
        self.assertFalse(observed.output_on)


if __name__ == "__main__":
    unittest.main()
