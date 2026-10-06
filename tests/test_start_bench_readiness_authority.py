from pathlib import Path
import unittest

from application.production_start_execution_port import ProductionStartMode
from application.production_start_route import ProductionStartRouteAdapter


ROOT = Path(__file__).resolve().parents[1]


class StartBenchReadinessAuthorityTests(unittest.TestCase):
    def test_production_route_default_is_active(self):
        self.assertEqual(
            ProductionStartRouteAdapter.__init__.__kwdefaults__["mode"],
            ProductionStartMode.ACTIVE,
        )

    def test_retired_activation_policy_is_not_executable_authority(self):
        self.assertFalse((ROOT / "application" / "start_activation_policy.py").exists())
        source = (ROOT / "application" / "production_start_execution_port.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("StartActivationPolicy", source)
        self.assertNotIn("explicit_active_enable", source)

    def test_current_docs_do_not_claim_dry_run_production_default(self):
        route = (ROOT / "docs" / "V3_START_PRODUCTION_ROUTE_WIRING.md").read_text(
            encoding="utf-8"
        )
        gate = (ROOT / "docs" / "V3_START_ACTIVATION_GATE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("ACTIVE by default", route)
        self.assertIn("deliberately removed", gate)
        self.assertNotIn("production default is `DRY_RUN`", route)


if __name__ == "__main__":
    unittest.main()
