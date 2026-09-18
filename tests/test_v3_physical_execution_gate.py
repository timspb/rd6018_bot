import unittest
from pathlib import Path
from types import SimpleNamespace

from runtime.output.bridge import PhysicalExecutionConfig, PhysicalExecutionError, PhysicalExecutionGate, PhysicalGateState
from runtime.output.intent import OutputAction


class PhysicalExecutionGateTests(unittest.TestCase):
    def test_independent_executor_is_not_exported(self):
        import runtime.output.bridge as bridge

        self.assertFalse(hasattr(bridge, "PhysicalBridgeExecutor"))
        source = (Path(__file__).resolve().parents[1] / "runtime" / "output" / "bridge" / "executor.py").read_text(encoding="utf-8")
        self.assertNotIn("class PhysicalBridgeExecutor", source)

    def test_gate_is_disabled_by_default(self):
        gate = PhysicalExecutionGate()
        with self.assertRaises(PhysicalExecutionError):
            gate.arm("operator")
        self.assertEqual(gate.state, PhysicalGateState.DISABLED)

    def test_gate_requires_manual_arm_before_validation(self):
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        plan = SimpleNamespace(intent=SimpleNamespace(action=OutputAction.DISABLE), protection_ovp=None, protection_ocp=None)
        validation = gate.validate(plan, type("Safety", (), {"allowed": True})(), None, None)
        self.assertFalse(validation.allowed)
        self.assertIn("manual_arm_required", validation.violations)
        gate.arm("operator")
        self.assertEqual(gate.state, PhysicalGateState.ARMED)


if __name__ == "__main__":
    unittest.main()
