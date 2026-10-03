"""Contracts for the modular MAIN authority/config extraction."""

from __future__ import annotations

from pathlib import Path
import unittest

import v2_authority
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from runtime.charge.strategy.main_authority import decide_main_transition
from runtime.charge.strategy.main_targets import select_main_target
from runtime.charge.strategy.main_variables import (
    AGM_MAX_RECOVERY_ATTEMPTS,
    AGM_PLATEAU_REQUIRED_MINUTES,
    AGM_STAGE_VOLTAGES_V,
    AGM_TAIL_HOLD_HOURS,
    AGM_TIMEOUT_TAIL_CURRENT_A,
    CA_MAIN_VOLTAGE_V,
    DEFAULT_MAIN_VOLTAGE_V,
    EFB_MAIN_VOLTAGE_V,
    MAIN_CURRENT_C_RATE,
    MAIN_FALLBACK_HOURS,
    NEAR_TARGET_MARGIN_V,
    PLATEAU_EVIDENCE_WINDOW_MINUTES,
    STANDARD_MAX_RECOVERY_ATTEMPTS,
    STANDARD_PLATEAU_REQUIRED_MINUTES,
    STANDARD_TAIL_HOLD_HOURS,
)
from runtime.safety.variables import MAX_STAGE_CURRENT_A


ROOT = Path(__file__).resolve().parents[1]


class V3MainAuthorityMigrationTests(unittest.TestCase):
    def test_compatibility_surface_reexports_canonical_main_owner(self) -> None:
        self.assertIs(v2_authority.decide_main_transition, decide_main_transition)
        self.assertIs(v2_authority.AuthorityAction, AuthorityAction)
        self.assertIs(v2_authority.AuthorityDecision, AuthorityDecision)
        self.assertEqual(
            v2_authority.AGM_TIMEOUT_TAIL_CURRENT_A,
            float(AGM_TIMEOUT_TAIL_CURRENT_A.default),
        )

    def test_main_variable_metadata_is_complete(self) -> None:
        variables = (
            AGM_MAX_RECOVERY_ATTEMPTS,
            AGM_PLATEAU_REQUIRED_MINUTES,
            AGM_STAGE_VOLTAGES_V,
            AGM_TAIL_HOLD_HOURS,
            AGM_TIMEOUT_TAIL_CURRENT_A,
            CA_MAIN_VOLTAGE_V,
            DEFAULT_MAIN_VOLTAGE_V,
            EFB_MAIN_VOLTAGE_V,
            MAIN_CURRENT_C_RATE,
            MAIN_FALLBACK_HOURS,
            NEAR_TARGET_MARGIN_V,
            PLATEAU_EVIDENCE_WINDOW_MINUTES,
            STANDARD_MAX_RECOVERY_ATTEMPTS,
            STANDARD_PLATEAU_REQUIRED_MINUTES,
            STANDARD_TAIL_HOLD_HOURS,
        )
        for spec in variables:
            self.assertTrue(spec.key)
            self.assertEqual(spec.owner, "runtime.charge.strategy.main")
            self.assertTrue(spec.unit)
            self.assertTrue(spec.description)
            self.assertTrue(spec.provenance)

    def test_accepted_main_targets_are_preserved(self) -> None:
        ca = select_main_target(profile="Ca/Ca", capacity_ah=90, agm_stage_idx=0)
        efb = select_main_target(profile="EFB", capacity_ah=90, agm_stage_idx=0)
        agm0 = select_main_target(profile="AGM", capacity_ah=90, agm_stage_idx=0)
        agm3 = select_main_target(profile="AGM", capacity_ah=90, agm_stage_idx=3)

        self.assertEqual((ca.voltage_v, ca.current_a), (14.7, 9.0))
        self.assertEqual((efb.voltage_v, efb.current_a), (14.8, 9.0))
        self.assertEqual((agm0.voltage_v, agm0.current_a), (14.4, 9.0))
        self.assertEqual((agm3.voltage_v, agm3.current_a), (15.0, 9.0))

        high_capacity = select_main_target(profile="AGM", capacity_ah=200, agm_stage_idx=0)
        self.assertEqual(high_capacity.current_a, float(MAX_STAGE_CURRENT_A.default))

    def test_accepted_main_variable_values_are_explicit(self) -> None:
        self.assertEqual(float(MAIN_FALLBACK_HOURS.default), 72.0)
        self.assertEqual(float(STANDARD_TAIL_HOLD_HOURS.default), 3.0)
        self.assertEqual(float(AGM_TAIL_HOLD_HOURS.default), 2.0)
        self.assertEqual(int(STANDARD_MAX_RECOVERY_ATTEMPTS.default), 3)
        self.assertEqual(int(AGM_MAX_RECOVERY_ATTEMPTS.default), 4)
        self.assertEqual(tuple(AGM_STAGE_VOLTAGES_V.default), (14.4, 14.6, 14.8, 15.0))
        self.assertEqual(float(AGM_TIMEOUT_TAIL_CURRENT_A.default), 0.20)

    def test_transitional_controllers_consume_modular_main_owner(self) -> None:
        auto = (ROOT / "auto_strategy_v2.py").read_text(encoding="utf-8")
        production = (ROOT / "production_controller.py").read_text(encoding="utf-8")
        controller = (ROOT / "charge_controller_v2.py").read_text(encoding="utf-8")
        compat = (ROOT / "v2_authority.py").read_text(encoding="utf-8")

        self.assertNotIn("from charge_logic import (\n    AGM_FIRST_STAGE_HOLD_SEC", auto)
        self.assertIn("from runtime.charge.strategy.main_authority import decide_main_transition", auto)
        self.assertIn("select_main_target(", production)
        self.assertNotIn("AGM_FIRST_STAGE_HOLD_SEC", production)
        for name in (
            "AGM_FIRST_STAGE_HOLD_SEC",
            "FIRST_STAGE_HOLD_SEC",
            "ANTISULFATE_MAX_AGM",
            "ANTISULFATE_MAX_CA_EFB",
            "AGM_STAGES",
        ):
            self.assertNotIn(name, controller)
        self.assertNotIn("def decide_main_transition(", compat)
        self.assertIn(
            "from runtime.charge.strategy.main_authority import",
            compat,
        )


if __name__ == "__main__":
    unittest.main()
