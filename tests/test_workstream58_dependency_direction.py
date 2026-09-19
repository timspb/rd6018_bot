import pathlib
import unittest

from application.charge_program import BatteryProfile, ProgramIdResolver


ROOT = pathlib.Path(__file__).parents[1]


class DependencyDirectionCleanupTests(unittest.TestCase):
    def test_program_id_aliases_resolve_outside_model(self):
        self.assertEqual(ProgramIdResolver.chemistry("CA_CA").value, "CALCIUM")
        self.assertEqual(ProgramIdResolver.chemistry("KAK").value, "CALCIUM")
        source = (ROOT / "application" / "charge_program" / "models.py").read_text(encoding="utf-8")
        self.assertNotIn("from .aliases", source)

    def test_pure_domain_files_do_not_import_infrastructure(self):
        paths = [
            ROOT / "application" / "charge_program" / "models.py",
            ROOT / "application" / "charge_engine" / "generic.py",
            ROOT / "application" / "charge_engine" / "phases" / "contracts.py",
            ROOT / "application" / "safety" / "policy.py",
        ]
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for forbidden in ("physical_adapter", "bench_transport", "ESPHome", "Modbus", "runtime.v2"):
                self.assertNotIn(forbidden, source, str(path))

    def test_dashboard_source_is_canonical(self):
        source = (ROOT / "application" / "operator_dashboard_composer.py").read_text(encoding="utf-8")
        self.assertIn("OperatorStateSnapshot", source)
        self.assertIn("CanonicalOperatorTimeline", source)
        self.assertNotIn("from .operator_runtime_view import", source)


if __name__ == "__main__":
    unittest.main()
