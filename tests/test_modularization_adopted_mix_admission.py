import ast
import inspect
import types
import unittest
from pathlib import Path

from pb_domain import BatteryChemistry
from rd_managed_adoption import ManagedAdoptionFingerprint
from rd_managed_mix import ManagedMixAdoptionCoordinator, _finite_nonnegative
from rd_live_adoption import MIX_HARD_LIMIT_HOURS
from runtime.charge.strategy.adopted_mix_admission import (
    require_adopted_mix_budget,
    require_adopted_mix_chemistry,
)
from runtime.safety.runtime_guard import RuntimeSafetyError


class AdoptedMixAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fp = ManagedAdoptionFingerprint(16.0, 3.0)

    def chemistry(self, chemistry, capacity=100.0, fp=None, *, absolute=8.0, tolerance=0.08):
        return require_adopted_mix_chemistry(
            chemistry, capacity, fp or self.fp,
            absolute_current_ceiling_a=absolute, tolerance=tolerance,
        )

    def test_supported_chemistries_accept_high_voltage_within_envelope(self):
        for chemistry in (BatteryChemistry.AGM, BatteryChemistry.EFB,
                          BatteryChemistry.CA_CA, BatteryChemistry.FLOODED):
            with self.subTest(chemistry=chemistry):
                policy = __import__("recipe_engine").POLICIES[chemistry]
                self.chemistry(chemistry, fp=ManagedAdoptionFingerprint(
                    policy.recovery_voltage_ceiling_v + 0.08, 3.0
                ))

    def test_chemistry_rejections_keep_existing_messages_and_order(self):
        with self.assertRaisesRegex(RuntimeSafetyError, "supported Pb chemistry"):
            self.chemistry(BatteryChemistry.CUSTOM)
        with self.assertRaisesRegex(RuntimeSafetyError, "positive battery capacity"):
            self.chemistry(BatteryChemistry.AGM, capacity=0)
        with self.assertRaisesRegex(RuntimeSafetyError, "already-running high-voltage Mix"):
            self.chemistry(BatteryChemistry.AGM, fp=ManagedAdoptionFingerprint(15.08, 3.0))
        with self.assertRaisesRegex(RuntimeSafetyError, r"live Mix voltage 16.39V exceeds agm envelope 16.30V"):
            self.chemistry(BatteryChemistry.AGM, fp=ManagedAdoptionFingerprint(16.39, 3.0))

    def test_voltage_and_current_tolerance_and_minimum_ceiling(self):
        self.chemistry(BatteryChemistry.AGM, capacity=100,
                       fp=ManagedAdoptionFingerprint(16.38, 3.08), absolute=20)
        with self.assertRaisesRegex(RuntimeSafetyError, "live Mix current 3.09A exceeds chemistry HV envelope 3.00A"):
            self.chemistry(BatteryChemistry.AGM, capacity=100,
                           fp=ManagedAdoptionFingerprint(16.0, 3.09), absolute=20)
        with self.assertRaisesRegex(RuntimeSafetyError, "live Mix current 3.09A exceeds chemistry HV envelope 2.50A"):
            self.chemistry(BatteryChemistry.AGM, capacity=100,
                           fp=ManagedAdoptionFingerprint(16.0, 3.09), absolute=2.5)

    def test_capacity_invalid_values_preserve_helper_contract(self):
        for value in (-1, True, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(RuntimeSafetyError):
                self.chemistry(BatteryChemistry.AGM, capacity=value)
        with self.assertRaisesRegex(RuntimeSafetyError, "battery capacity is required"):
            self.chemistry(BatteryChemistry.AGM, capacity=None)
        with self.assertRaisesRegex(RuntimeSafetyError, "battery capacity is invalid"):
            self.chemistry(BatteryChemistry.AGM, capacity="bad")
        self.assertIs(_finite_nonnegative, __import__(
            "runtime.charge.strategy.adopted_mix_admission", fromlist=["_finite_nonnegative"]
        )._finite_nonnegative)

    def test_budget_rejects_at_floor_and_accepts_just_below(self):
        limit_s = MIX_HARD_LIMIT_HOURS[BatteryChemistry.AGM] * 3600.0
        require_adopted_mix_budget(BatteryChemistry.AGM, limit_s - 0.01)
        with self.assertRaisesRegex(RuntimeSafetyError, r"prior Mix age 10.00h already exhausts agm hard limit 10h"):
            require_adopted_mix_budget(BatteryChemistry.AGM, limit_s)
        with self.assertRaisesRegex(RuntimeSafetyError, "chemistry has no hard Mix limit"):
            require_adopted_mix_budget(BatteryChemistry.CUSTOM, 0)

    def test_coordinator_methods_are_thin_delegates(self):
        coordinator = ManagedMixAdoptionCoordinator.__new__(ManagedMixAdoptionCoordinator)
        coordinator.guard = types.SimpleNamespace(
            policy=types.SimpleNamespace(absolute_current_ceiling_a=8.0)
        )
        coordinator._chemistry_preflight(BatteryChemistry.AGM, 100, self.fp)
        coordinator._require_budget(BatteryChemistry.AGM, 0)
        with self.assertRaises(RuntimeSafetyError):
            coordinator._chemistry_preflight(
                BatteryChemistry.AGM, True, self.fp
            )
        source = inspect.getsource(ManagedMixAdoptionCoordinator)
        self.assertIn("require_adopted_mix_chemistry(", source)
        self.assertIn("require_adopted_mix_budget(chemistry, prior_elapsed_s)", source)

    def test_module_has_no_runtime_owner_import_or_physical_calls(self):
        path = Path(__file__).parents[1] / "runtime/charge/strategy/adopted_mix_admission.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertNotIn("rd_managed_mix", imports)
        self.assertNotIn("runtime.production_runtime", imports)
        calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)]
        self.assertFalse(set(calls) & {"turn_on", "turn_off", "set_voltage", "set_current"})


if __name__ == "__main__":
    unittest.main()
