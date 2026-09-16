"""Phase 7.1 pure-domain parity/golden tests."""

from __future__ import annotations

from pathlib import Path
import unittest

from runtime.charge import ChargeEngine, ChargeState, Measurements, ProfileRegistry, SessionManager, SessionStatus
from runtime.charge.programs import DeltaConfig, DeltaProgram


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "RD6018_DOMAIN_RUNTIME_PARITY.md"


class DomainRuntimeParityTests(unittest.TestCase):
    def test_transition_parity_golden_scenarios(self) -> None:
        engine = ChargeEngine.__new__(ChargeEngine)
        state = ChargeState(stage="prep")
        engine.transition(state, "main")
        engine.transition(state, "mix")
        with self.assertRaises(ValueError):
            engine.transition(state, "idle")

    def test_profile_parity_golden_values(self) -> None:
        registry = ProfileRegistry.with_defaults()
        agm = registry.get("AGM").recipe
        efb = registry.get("EFB").recipe
        calcium = registry.get("CA_CA").recipe
        self.assertEqual(15.0, agm.main.config.target_voltage)
        self.assertEqual(7200.0, agm.main.config.tail_hold_seconds)
        self.assertEqual(86400.0, efb.mix.config.active_authority_seconds)
        self.assertEqual(16.5, efb.mix.config.cc.target_voltage)
        self.assertEqual(16.5, calcium.mix.config.cc.target_voltage)
        self.assertEqual(72000.0, calcium.mix.config.active_authority_seconds)

    def test_custom_contract_is_explicit(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("explicit Main V/I, user Delta and time limit", text)
        with self.assertRaises(KeyError):
            ProfileRegistry.with_defaults().get("CUSTOM")

    def test_cv_delta_golden_hold_behavior(self) -> None:
        battery = ProfileRegistry.with_defaults().create_battery("AGM", 70)
        program = DeltaProgram(battery, DeltaConfig(16.3, 2.4, "CV", 0.2, 0.06, confirmations_required=2, hold_seconds=10.0))
        state = ChargeState(stage="mix")
        program.evaluate(state, Measurements(16.3, 0.2, time=0.0))
        program.evaluate(state, Measurements(16.3, 0.27, time=1.0))
        intent = program.evaluate(state, Measurements(16.3, 0.27, time=2.0))
        self.assertEqual("confirmed_hold", intent.next_stage)
        done = program.evaluate(state, Measurements(16.3, 0.27, time=12.0))
        self.assertTrue(done.completed)

    def test_cc_difference_is_explicitly_unresolved(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("Vmax then confirmed Delta-V", text)
        self.assertIn("captures reference current and detects current drop", text)
        self.assertIn("UNRESOLVED parity blocker", text)

    def test_session_parity_and_restart_candidate(self) -> None:
        manager = SessionManager()
        self.assertEqual(SessionStatus.ACTIVE, manager.start("s-1", "AGM").status)
        self.assertEqual(SessionStatus.PAUSED, manager.pause().status)
        self.assertEqual(SessionStatus.ACTIVE, manager.resume().status)
        self.assertEqual(SessionStatus.STOPPED, manager.stop().status)
        with self.assertRaises(ValueError):
            manager.resume()
        self.assertIn("restart is a candidate restore", DOC.read_text(encoding="utf-8"))

    def test_parity_document_tracks_keep_change_unresolved(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for marker in ("### KEEP", "### CHANGE", "### UNRESOLVED", "FSM parity", "Profile parity"):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
