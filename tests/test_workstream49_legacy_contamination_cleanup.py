import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
PROGRAM = ROOT / "application" / "charge_program"
ENGINE = ROOT / "application" / "charge_engine"
CORE = ROOT / "v3_core"


class V3LegacyContaminationCleanupTests(unittest.TestCase):
    def test_resolver_is_selection_only(self):
        source = (PROGRAM / "resolver.py").read_text(encoding="utf-8")
        for forbidden in ("AUTO_PROGRAM_DEFAULTS", "main_voltage_v", "mix_voltage_v", "Timer(", "Phase(", "SafetyPolicy("):
            self.assertNotIn(forbidden, source)

    def test_one_canonical_engine(self):
        source = (ENGINE / "engine.py").read_text(encoding="utf-8")
        self.assertIn("GenericChargeEngine", source)
        self.assertNotIn("class ChargeEngine", source)

    def test_aliases_are_boundary_mapping_only(self):
        from application.charge_program import ProgramIdentityRegistry
        registry = ProgramIdentityRegistry()
        self.assertEqual(registry.canonical_id("CA_CA"), "CALCIUM")
        self.assertEqual(registry.canonical_id("KAK"), "CALCIUM")

    def test_pure_core_has_no_infrastructure_imports(self):
        for path in (CORE / "domain.py", CORE / "contracts.py", CORE / "safety.py", CORE / "composition.py", CORE / "execution.py"):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("physical_adapter", "bench_transport", "HA", "ESPHome", "Modbus", "runtime.v2"):
                self.assertNotIn(forbidden, source, str(path))


if __name__ == "__main__":
    unittest.main()
