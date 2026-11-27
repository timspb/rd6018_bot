"""Standing owner policy: OVP/OCP are observable, never software charge gates."""
from __future__ import annotations

import unittest

from runtime.safety.telemetry_recovery import isolated_callback_recovery_eligible


def _live(protection_code):
    return {
        "switch": "on",
        "protection_code": protection_code,
        "ovp_triggered": "on",
        "ocp_triggered": "on",
        "_meta": {
            "switch": {"status": "ok", "age_s": 0.1},
            "protection_code": {"status": "ok", "age_s": 0.1},
        },
    }


class OvpOcpObservationOnlyTests(unittest.TestCase):
    def eligible(self, code):
        return isolated_callback_recovery_eligible(
            _live(code),
            "critical runtime telemetry is stale/incoherent: battery_voltage stale age=22.0s>20.0s",
            output_known=True,
            max_voltage_v=18.0,
            max_current_a=12.0,
            critical_battery_temp_c=48.0,
            max_psu_temp_c=55.0,
        )

    def test_ovp_ocp_r16_codes_and_legacy_bits_do_not_block_recovery_wait(self):
        for code in (0, 1, 2):
            with self.subTest(r16=code):
                self.assertTrue(self.eligible(code))

    def test_opp_r16_code_blocks_recovery_wait(self):
        self.assertFalse(self.eligible(3))


if __name__ == "__main__":
    unittest.main()
