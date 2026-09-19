import unittest

from application.v3_observer_composition import V3ObserverComposition


class Workstream36ObserverLiveRunValidationTests(unittest.TestCase):
    def test_snapshot_pipeline_to_telegram(self):
        composition = V3ObserverComposition()
        state = composition.snapshot({"persisted": {"state": "active", "stage": "mix", "request": {"battery_id": "Baic72"}}, "telemetry": {"voltage": 17.14, "current": 3.48, "temperature": 35.0, "source": "supplied-live-fixture"}, "rd": {"phase": "mix"}, "esphome": {"output": True}, "ha": {"available": True}, "explanation": {"safety_state": "NORMAL", "strategy": "MIX_HOLD", "reason": "observed"}, "canary": {"status": "BLOCKED"}})
        message = composition.telegram_message(state)
        self.assertTrue(state.observe_only)
        self.assertIn("Baic72", message)
        self.assertIn("MIX_HOLD", message)

    def test_missing_live_sources_degrade_to_unknown(self):
        composition = V3ObserverComposition(evidence_reader=lambda: (_ for _ in ()).throw(RuntimeError("source unavailable")), telemetry_reader=lambda: (_ for _ in ()).throw(RuntimeError("source unavailable")))
        state = composition.snapshot({"persisted": {"state": "active", "stage": "mix"}})
        self.assertEqual("UNKNOWN", state.telemetry.source)
        self.assertIn("evidence", composition.lifecycle.degraded_sources)
        self.assertIn("telemetry", composition.lifecycle.degraded_sources)
        self.assertIn("UNKNOWN", composition.telegram_message(state))

    def test_single_snapshot_is_used(self):
        composition = V3ObserverComposition()
        state = composition.snapshot({"persisted": {"state": "active", "stage": "mix"}, "telemetry": {"voltage": 17.1, "current": 3.4}})
        self.assertEqual(state.telemetry.stale_indicators, state.safety.stale)
        self.assertTrue(state.observe_only)

    def test_no_control_surface(self):
        composition = V3ObserverComposition()
        self.assertFalse(hasattr(composition, "start_charge"))
        self.assertFalse(hasattr(composition, "stop_charge"))
        self.assertFalse(hasattr(composition, "execute"))


if __name__ == "__main__":
    unittest.main()
