from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from production_controller import ProductionChargeController


ROOT = Path(__file__).resolve().parents[1]


class DummyHass:
    pass


class V3ResidualAuthorityMigrationTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self) -> ProductionChargeController:
        controller = ProductionChargeController(DummyHass(), authoritative=True)
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 60
        controller.stage_start_time = 100.0
        controller.total_start_time = 100.0
        controller._stage_start_ah = 1.0
        controller._last_known_output_on = True
        controller._save_session = lambda *args, **kwargs: None
        return controller

    async def test_prep_transition_is_owned_without_historical_tick(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_PREP

        with patch("charge_controller.time.time", return_value=1000.0):
            actions = await controller._run_stage_scaffold_tick(
                stage_before=controller.STAGE_PREP,
                voltage=12.0,
                current=0.6,
                temp_ext=25.0,
                is_cv=False,
                ah=2.0,
                output_is_on=True,
                manual_off_active=False,
                is_cc=True,
                manual_active=False,
            )

        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)
        expected_v, expected_i = controller._main_target(25.0)
        self.assertAlmostEqual(actions["set_voltage"], expected_v, places=3)
        self.assertAlmostEqual(actions["set_current"], expected_i, places=3)
        self.assertIn("set_ovp", actions)
        self.assertIn("set_ocp", actions)

    async def test_cooling_resume_is_owned_without_historical_tick(self):
        controller = self._controller()
        controller.current_stage = controller.STAGE_COOLING
        controller._cooling_from_stage = controller.STAGE_PREP
        controller._cooling_target_v = 12.0
        controller._cooling_target_i = 0.6

        with patch("charge_controller.time.time", return_value=1200.0):
            actions = await controller._run_stage_scaffold_tick(
                stage_before=controller.STAGE_COOLING,
                voltage=11.9,
                current=0.0,
                temp_ext=35.0,
                is_cv=False,
                ah=2.0,
                output_is_on=False,
                manual_off_active=False,
                is_cc=True,
                manual_active=False,
            )

        self.assertEqual(controller.current_stage, controller.STAGE_PREP)
        self.assertTrue(actions["turn_on"])
        self.assertEqual(actions["set_voltage"], 12.0)
        self.assertEqual(actions["set_current"], 0.6)

    async def test_unknown_stage_fails_closed_instead_of_falling_back(self):
        controller = self._controller()
        controller.current_stage = "synthetic-unknown"
        controller._clear_session_file = lambda: None

        with patch("charge_controller.time.time", return_value=1300.0):
            actions = await controller._run_stage_scaffold_tick(
                stage_before="synthetic-unknown",
                voltage=13.0,
                current=0.1,
                temp_ext=25.0,
                is_cv=False,
                ah=2.0,
                output_is_on=True,
                manual_off_active=False,
                is_cc=True,
                manual_active=False,
            )

        self.assertTrue(actions["turn_off"])
        self.assertEqual(actions["log_event"], "HISTORICAL_STAGE_RUNTIME_RETIRED")
        self.assertEqual(controller.current_stage, controller.STAGE_IDLE)


class V3ResidualAuthorityStaticTests(unittest.TestCase):
    def test_v2_controller_has_no_historical_tick_fallback(self):
        source = (ROOT / "charge_controller.py").read_text(encoding="utf-8")
        self.assertNotIn("super().tick(", source)
        self.assertIn("run_authoritative_residual_scaffold(", source)

    def test_residual_scaffold_has_no_historical_controller_dependency(self):
        source = (
            ROOT / "runtime" / "charge" / "runtime" / "residual_scaffold.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("charge_logic", source)
        self.assertNotIn("super().tick", source)
        self.assertIn("STAGE_TRANSITION_BLANKING_S", source)


if __name__ == "__main__":
    unittest.main()
