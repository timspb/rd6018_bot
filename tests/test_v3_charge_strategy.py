import ast
import pathlib
import unittest

from runtime.charge import BatteryProfile, ChemistryProfile, Measurements
from runtime.charge.strategy import (
    CCMixExitConfig, CVMixExitConfig, ChargeRecipe, ChargeStrategy,
    MainPolicy, MainPolicyConfig, MixPolicy, MixPolicyConfig,
    RecoveryPolicy, RecoveryPolicyConfig, StrategyRuntimeState,
)


class V3ChargeStrategyTests(unittest.TestCase):
    def setUp(self):
        main = MainPolicy(MainPolicyConfig(14.8, 5.0, 0.3, 10.0, 0.4, 10.0))
        recovery = RecoveryPolicy(RecoveryPolicyConfig(2, 16.3, 1.0))
        cc = CCMixExitConfig(16.5, 0.03, 2, 10.0, 16.5, 2.0)
        cv = CVMixExitConfig(0.4, 0.1, 2, 10.0, 16.5, 2.0)
        mix = MixPolicy(MixPolicyConfig(100.0, cc, cv))
        self.strategy = ChargeStrategy(BatteryProfile(ChemistryProfile.EFB, 70.0), ChargeRecipe(main, recovery, mix))

    def test_main_normal_tail_completes_without_delta(self):
        state = StrategyRuntimeState()
        self.strategy.evaluate(state, Measurements(14.8, 0.3, 25.0, 0.0))
        result = self.strategy.evaluate(state, Measurements(14.8, 0.3, 25.0, 10.0))
        self.assertTrue(result.completed)
        self.assertEqual("done", result.next_stage)

    def test_main_plateau_enters_recovery_then_returns_main(self):
        state = StrategyRuntimeState()
        self.strategy.evaluate(state, Measurements(14.8, 0.5, 25.0, 0.0))
        result = self.strategy.evaluate(state, Measurements(14.8, 0.5, 25.0, 10.0))
        self.assertEqual("recovery", result.next_stage)
        self.assertEqual("main", self.strategy.evaluate(state, Measurements(14.8, 0.5, 25.0, 11.0)).next_stage)

    def test_recovery_exhausted_enters_mix_without_delta(self):
        state = StrategyRuntimeState()
        self.strategy.recipe.recovery.state.attempts = 2
        self.strategy.evaluate(state, Measurements(14.8, 0.5, 25.0, 0.0))
        result = self.strategy.evaluate(state, Measurements(14.8, 0.5, 25.0, 10.0))
        self.assertEqual("mix", result.next_stage)

    def test_mix_cc_vmax_delta_hold_exit(self):
        state = StrategyRuntimeState(stage="mix")
        self.strategy.evaluate(state, Measurements(16.5, 2.0, 25.0, 0.0), mix_mode="CC")
        self.strategy.evaluate(state, Measurements(16.47, 2.0, 25.0, 1.0), mix_mode="CC")
        result = self.strategy.evaluate(state, Measurements(16.46, 2.0, 25.0, 2.0), mix_mode="CC")
        self.assertEqual("MIX_CC_DELTA_CONFIRMED", result.reason)
        result = self.strategy.evaluate(state, Measurements(16.46, 2.0, 25.0, 12.0), mix_mode="CC")
        self.assertTrue(result.completed)

    def test_mix_cv_imin_delta_hold_exit(self):
        state = StrategyRuntimeState(stage="mix")
        self.strategy.evaluate(state, Measurements(16.5, 0.4, 25.0, 0.0), mix_mode="CV")
        self.strategy.evaluate(state, Measurements(16.5, 0.5, 25.0, 1.0), mix_mode="CV")
        result = self.strategy.evaluate(state, Measurements(16.5, 0.5, 25.0, 2.0), mix_mode="CV")
        self.assertEqual("MIX_CV_DELTA_CONFIRMED", result.reason)
        self.assertTrue(self.strategy.evaluate(state, Measurements(16.5, 0.5, 25.0, 12.0), mix_mode="CV").completed)

    def test_strategy_domain_has_no_infrastructure_imports(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge" / "strategy"
        forbidden = {"pb_domain", "hass_api", "aiogram", "rd_control_mode", "safe_output", "bot_legacy"}
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden, str(path))

    def test_recipe_rejects_invalid_profile_values(self):
        with self.assertRaises(ValueError):
            CCMixExitConfig(16.5, 0.0, 2, 10.0, 16.5, 2.0)
        with self.assertRaises(ValueError):
            CVMixExitConfig(0.4, 0.1, 0, 10.0, 16.5, 2.0)
        with self.assertRaises(ValueError):
            MixPolicyConfig(-1.0, self.strategy.recipe.mix.config.cc, self.strategy.recipe.mix.config.cv)


if __name__ == "__main__":
    unittest.main()
