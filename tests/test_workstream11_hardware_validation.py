import ast
import unittest
from pathlib import Path

from v3_core.hardware_validation import (
    RealObservation,
    RealReadbackObservation,
    RealReadbackValidationModel,
    RealTelemetryValidationModel,
    ReadbackValidationStatus,
    RealValidationStatus,
    ShadowComparisonCategory,
    compare_shadow_observation,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream11HardwareValidationTests(unittest.TestCase):
    def test_telemetry_statuses(self):
        model = RealTelemetryValidationModel()
        good = RealObservation("ESP_DIRECT", 1.0, 1.0, 1.0, True, {"voltage": 14.8})
        ha = RealObservation("HA", 1.0, 1.0, 1.0, True, {"voltage": 14.8})
        self.assertEqual(RealValidationStatus.VERIFIED, model.validate((good, ha)))
        self.assertEqual(RealValidationStatus.CONFLICT, model.validate((good, RealObservation("HA", 1.0, 1.0, 1.0, True, {"voltage": 14.5}))))
        self.assertEqual(RealValidationStatus.DEGRADED, model.validate((RealObservation("HA", 1.0, 30.0, 1.0, True, {}),)))
        self.assertEqual(RealValidationStatus.UNAVAILABLE, model.validate((RealObservation("HA", 1.0, 1.0, 0.0, False, {}),)))

    def test_readback_never_equates_acceptance_with_verification(self):
        model = RealReadbackValidationModel()
        base = dict(command_id="c1", requested={"output": "ON"}, observed={"output": "ON"}, age_s=1.0, available=True)
        self.assertEqual(ReadbackValidationStatus.VERIFIED, model.validate(RealReadbackObservation(matches=True, **base)))
        self.assertEqual(ReadbackValidationStatus.MISMATCH, model.validate(RealReadbackObservation(matches=False, **base)))
        self.assertEqual(ReadbackValidationStatus.STALE, model.validate(RealReadbackObservation(matches=True, **{**base, "age_s": 30.0})))
        self.assertEqual(ReadbackValidationStatus.UNAVAILABLE, model.validate(RealReadbackObservation(matches=None, **{**base, "observed": None, "available": False})))

    def test_shadow_comparison_and_no_write_symbols(self):
        result = compare_shadow_observation({"phase": "CV"}, {"phase": "CV"})
        self.assertEqual(ShadowComparisonCategory.MATCH, result.category)
        source = (ROOT / "v3_core" / "hardware_validation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"set_voltage", "set_current", "output_on", "output_off", "turn_on", "turn_off", "write"}
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse(forbidden & (names | attrs))


if __name__ == "__main__":
    unittest.main()
