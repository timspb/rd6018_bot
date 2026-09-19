import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from v3_core import V3Composition
from v3_core.contracts import ActuatorIntent, ActuatorOperation, TelemetrySnapshot


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "v3_core"


class Workstream4V3CoreTests(unittest.TestCase):
    def test_core_has_no_legacy_or_infrastructure_imports(self):
        forbidden = ("application", "runtime", "hass_api", "rd6018_telemetry", "edge_safety_lease", "safe_output")
        for path in CORE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = node.module if isinstance(node, ast.ImportFrom) else None
                names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
                self.assertFalse(module and module.startswith(forbidden), (path.name, module))
                self.assertFalse(any(name.startswith(forbidden) for name in names), (path.name, names))

    def test_standalone_composition_is_constructible_without_runtime(self):
        composition = V3Composition.standalone()
        self.assertEqual("V3 Charge Domain", composition.domain.owner)
        self.assertEqual("V3 Safety Domain", composition.safety.owner)

    def test_actuator_path_is_single_shadow_boundary(self):
        composition = V3Composition.standalone()
        intent = ActuatorIntent(ActuatorOperation.SET_VOLTAGE, 14.7, "test", "trace-4")
        result = composition.execution.dispatch(intent)
        self.assertTrue(result.accepted)
        self.assertFalse(result.executed)

    def test_safety_decision_is_canonical_and_nonphysical(self):
        composition = V3Composition.standalone()
        telemetry = TelemetrySnapshot(None, None, None, None, datetime.now(timezone.utc), "test", 30.0)
        decision = composition.domain.evaluate(telemetry, trace_id="trace-safety")
        self.assertEqual("CONTAINMENT_REQUIRED", decision.state)
        self.assertIsNotNone(decision.intent)
        result = composition.execution.dispatch(decision.intent)
        self.assertFalse(result.executed)

    def test_configuration_rejects_unknown_values(self):
        authority = V3Composition.standalone().configuration
        with self.assertRaises(ValueError):
            authority.resolve({"not_v3": 1})


if __name__ == "__main__":
    unittest.main()
