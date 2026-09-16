"""Phase 7.0 pure domain runtime skeleton tests."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.charge import (
    ChargeEngine,
    ChargeState,
    Measurements,
    ProfileRegistry,
    SessionManager,
    SessionStatus,
    StrategyEngine,
)


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "runtime" / "charge"
SKELETON_FILES = (
    DOMAIN / "decisions.py",
    DOMAIN / "engine.py",
    DOMAIN / "profile_registry.py",
    DOMAIN / "strategy_engine.py",
    DOMAIN / "session.py",
)


class DomainRuntimeSkeletonTests(unittest.TestCase):
    def test_fsm_transitions_and_invalid_transition(self) -> None:
        self.assertIn("main", ChargeEngine.TRANSITIONS["prep"])
        self.assertIn("mix", ChargeEngine.TRANSITIONS["main"])
        engine = ChargeEngine.__new__(ChargeEngine)
        state = ChargeState(stage="prep")
        self.assertEqual("main", engine.transition(state, "main").stage)
        with self.assertRaises(ValueError):
            engine.transition(state, "idle")

    def test_profile_registry_has_all_builtin_profiles(self) -> None:
        registry = ProfileRegistry.with_defaults()
        self.assertEqual(("agm", "ca_ca", "efb"), registry.available())
        for name in registry.available():
            self.assertGreater(registry.create_battery(name, 70).capacity_ah, 0)

    def test_strategy_decision_is_pure_domain_output(self) -> None:
        battery = ProfileRegistry.with_defaults().create_battery("AGM", 70)
        strategy = StrategyEngine(battery)
        intent = strategy.evaluate(ChargeState(stage="main"), Measurements(voltage=14.8, current=1.0, time=1.0))
        self.assertIsNotNone(intent)
        self.assertIsNotNone(intent.target_voltage)

    def test_session_lifecycle(self) -> None:
        manager = SessionManager()
        self.assertEqual(SessionStatus.IDLE, manager.snapshot.status)
        self.assertEqual(SessionStatus.ACTIVE, manager.start("s1", "AGM").status)
        self.assertEqual(SessionStatus.PAUSED, manager.pause().status)
        self.assertEqual(SessionStatus.ACTIVE, manager.resume().status)
        self.assertEqual(SessionStatus.STOPPED, manager.stop().status)
        with self.assertRaises(ValueError):
            manager.resume()

    def test_domain_package_has_no_infrastructure_or_ui_imports(self) -> None:
        forbidden = (
            "application", "telegram", "aiogram", "hass_api", "homeassistant",
            "esphome", "rd_transport", "persistence", "database", "runtime.physical",
            "runtime.output", "runtime.ui", "serial", "modbus",
        )
        violations: list[str] = []
        for path in SKELETON_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if any(token in name.lower() for token in forbidden):
                        violations.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual([], violations)

    def test_domain_document_declares_no_runtime_wiring(self) -> None:
        text = (ROOT / "docs" / "RD6018_DOMAIN_RUNTIME_MODEL.md").read_text(encoding="utf-8")
        for term in ("ChargeEngine", "ProfileRegistry", "StrategyEngine", "SessionManager", "No executor", "physical\ncommand"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
