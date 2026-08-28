import unittest

from recovery_replay import replay_document


class RecoveryReplayTests(unittest.TestCase):
    @staticmethod
    def _cycle(battery_id, offset, capacity, cca, ri, current_scale=1.0):
        return {
            "battery_id": battery_id,
            "started_at": offset,
            "completed_at": offset + 1800,
            "intent": "recovery",
            "condition_before": "rehydrated",
            "measured_capacity_ah": capacity,
            "cca_a": cca,
            "internal_resistance_mohm": ri,
            "trace": [
                {
                    "timestamp_s": offset,
                    "stage": "Main Charge",
                    "voltage_v": 14.2,
                    "current_a": 1.0 * current_scale,
                    "temp_c": 25.0,
                    "is_cv": True,
                    "target_voltage_v": 14.8,
                    "ah": 10.0,
                },
                {
                    "timestamp_s": offset + 300,
                    "stage": "Main Charge",
                    "voltage_v": 14.7,
                    "current_a": 0.4 * current_scale,
                    "temp_c": 25.2,
                    "is_cv": True,
                    "target_voltage_v": 14.8,
                    "ah": 10.3,
                },
                {
                    "timestamp_s": offset + 600,
                    "stage": "Mix Mode",
                    "voltage_v": 16.4,
                    "current_a": 0.25 * current_scale,
                    "temp_c": 25.4,
                    "is_cv": True,
                    "target_voltage_v": 16.5,
                    "ah": 10.5,
                },
                {
                    "timestamp_s": offset + 900,
                    "stage": "relax",
                    "voltage_v": 13.5,
                    "current_a": 0.0,
                    "temp_c": 25.2,
                    "ah": 10.5,
                },
                {
                    "timestamp_s": offset + 1200,
                    "stage": "relax",
                    "voltage_v": 13.2,
                    "current_a": 0.0,
                    "temp_c": 25.1,
                    "ah": 10.5,
                },
                {
                    "timestamp_s": offset + 1800,
                    "stage": "relax",
                    "voltage_v": 13.0,
                    "current_a": 0.0,
                    "temp_c": 25.0,
                    "ah": 10.5,
                },
            ],
        }

    def test_replay_produces_cycle_evidence_and_trend(self):
        result = replay_document(
            {
                "cycles": [
                    self._cycle("battery-1", 0, 40.0, 400.0, 8.0, 1.0),
                    self._cycle("battery-1", 10000, 45.0, 440.0, 7.0, 0.8),
                ]
            }
        )

        self.assertEqual(len(result["cycles"]), 2)
        self.assertEqual(result["trend"]["status"], "improving")
        self.assertEqual(result["trend"]["confidence"], "medium")
        self.assertGreater(result["trend"]["score"], 0)
        self.assertAlmostEqual(result["cycles"][0]["main_imin_a"], 0.4)
        self.assertAlmostEqual(result["cycles"][1]["main_imin_a"], 0.32)
        self.assertEqual(len(result["decision_traces"]), 2)
        self.assertGreater(result["decision_summary"]["counts"]["continue"], 0)
        # Imin changed substantially, but remains score-neutral evidence.
        imin_metric = next(
            metric for metric in result["trend"]["metrics"] if metric["name"] == "Main Imin"
        )
        self.assertEqual(imin_metric["score"], 0)

    def test_replay_surfaces_clean_hv_reversal_as_finish_decision(self):
        cycle = {
            "battery_id": "battery-reversal",
            "started_at": 0,
            "intent": "recovery",
            "trace": [
                {"timestamp_s": 0, "stage": "Main Charge", "voltage_v": 14.7, "current_a": 0.5, "temp_c": 25.0, "is_cv": True, "target_voltage_v": 14.8},
                {"timestamp_s": 600, "stage": "Mix Mode", "voltage_v": 16.40, "current_a": 0.40, "temp_c": 25.4, "is_cv": True, "target_voltage_v": 16.5},
                {"timestamp_s": 720, "stage": "Mix Mode", "voltage_v": 16.47, "current_a": 0.20, "temp_c": 25.4, "is_cv": True, "target_voltage_v": 16.5},
                {"timestamp_s": 840, "stage": "Mix Mode", "voltage_v": 16.49, "current_a": 0.20, "temp_c": 25.4, "is_cv": True, "target_voltage_v": 16.5},
                {"timestamp_s": 900, "stage": "Mix Mode", "voltage_v": 16.49, "current_a": 0.27, "temp_c": 25.5, "is_cv": True, "target_voltage_v": 16.5},
                {"timestamp_s": 960, "stage": "Mix Mode", "voltage_v": 16.49, "current_a": 0.28, "temp_c": 25.5, "is_cv": True, "target_voltage_v": 16.5},
                {"timestamp_s": 1020, "stage": "Mix Mode", "voltage_v": 16.49, "current_a": 0.29, "temp_c": 25.6, "is_cv": True, "target_voltage_v": 16.5},
            ],
        }
        result = replay_document({"cycles": [cycle]})
        first = result["decision_summary"]["first_non_continue"]
        self.assertIsNotNone(first)
        self.assertEqual(first["decision"], "finish_stage")
        self.assertIn("end_of_charge_likely", first["events"])

    def test_invalid_document_is_rejected(self):
        with self.assertRaises(ValueError):
            replay_document({"cycles": []})


if __name__ == "__main__":
    unittest.main()
