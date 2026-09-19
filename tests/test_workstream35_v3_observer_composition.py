import ast
import unittest
from pathlib import Path

from application.v3_observer_composition import V3ObserverComposition


class Workstream35V3ObserverCompositionTests(unittest.TestCase):
    def observations(self):
        return {"persisted": {"state": "active", "stage": "mix", "request": {"battery_id": "Baic72"}}, "telemetry": {"voltage": 17.14, "current": 3.48, "temperature": 35.0, "source": "HA+ESP"}, "rd": {"phase": "mix"}, "esphome": {"output": True}, "ha": {"available": True}, "explanation": {"safety_state": "NORMAL", "strategy": "MIX_HOLD", "reason": "observed"}, "canary": {"status": "BLOCKED", "blockers": ("CB-EVIDENCE-001",)}}

    def test_composition_lifecycle_is_idempotent(self):
        composition = V3ObserverComposition()
        self.assertTrue(composition.startup().started)
        self.assertTrue(composition.startup().started)
        self.assertTrue(composition.shutdown().shutdown)

    def test_snapshot_to_telegram_flow(self):
        composition = V3ObserverComposition()
        state = composition.snapshot(self.observations())
        message = composition.telegram_message(state)
        self.assertTrue(state.observe_only)
        self.assertIn("Baic72", message)
        self.assertIn("MIX_HOLD", message)
        self.assertIn("CONTROL: недоступен", message)

    def test_degraded_reader_becomes_unknown(self):
        composition = V3ObserverComposition(telemetry_reader=lambda: (_ for _ in ()).throw(RuntimeError("reader down")))
        state = composition.snapshot({"persisted": {"state": "active", "stage": "mix"}})
        self.assertEqual("UNKNOWN", state.telemetry.source)
        self.assertIn("telemetry", composition.lifecycle.degraded_sources)

    def test_no_command_capable_imports(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "v3_observer_composition.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {"aiogram", "aiohttp", "aioesphomeapi", "paramiko", "serial", "requests"})
        for token in ("output_on", "output_off", "turn_on", "turn_off", "controller.start", "controller.stop", "lease_renew", "send_command"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
