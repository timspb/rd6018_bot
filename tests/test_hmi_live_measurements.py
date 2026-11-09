"""Read-only HMI telemetry precedence and fallback."""
import unittest
from runtime.ui.components.hmi_live_measurements import _live_measurements
from runtime.ui.components.hmi_values import _regulator

class HmiLiveMeasurementsTests(unittest.TestCase):
    def test_native_rd_regulation_mode_is_used_and_unknown_is_not_guessed(self):
        self.assertEqual(_regulator({
            "regulation_mode": "cc", "regulation_code": 1,
            "is_cv": 0, "is_cc": 1,
        }), "CC")
        self.assertEqual(_regulator({
            "regulation_mode": "cv", "regulation_code": 0,
            "is_cv": 1, "is_cc": 0,
        }), "CV")
        self.assertEqual(_regulator({
            "regulation_mode": "unknown", "is_cv": 0, "is_cc": 0,
        }), "—")
        self.assertEqual(_regulator({
            "regulation_mode": "unknown", "is_cv": 1, "is_cc": 1,
        }), "—")
    def test_v2_temperature_wins_over_legacy(self):
        result=_live_measurements({
            "switch":"on", "battery_voltage":"12.80", "current":"1.05",
            "power":"13.44", "temp_ext_v2":"24", "temp_ext":"33",
            "temp_int_v2":"38", "temp_int":"45",
            "set_voltage":"14.7", "set_current":"7.2"
        })
        self.assertEqual(result, (True,12.8,1.05,13.44,24.,38.,14.7,7.2))
    def test_invalid_v2_uses_legacy_order_and_no_fabrication(self):
        result=_live_measurements({
            "switch":"off", "temp_ext_v2":float("nan"), "temp_ext":"25",
            "temp_int_v2":None, "temp_int":"bad",
            "psu_temperature":"42", "power_supply_temperature":"51",
            "current":float("inf")
        })
        self.assertEqual(result, (False,None,None,None,25.,42.,None,None))
    def test_missing_measurements_do_not_change_output_identity(self):
        self.assertEqual(_live_measurements({"switch": "on"})[0],True)
        self.assertEqual(_live_measurements({})[0],False)
