import ast
import pathlib
import unittest
from dataclasses import replace

from runtime.charge import BatteryProfile, ChargeEngine, ChemistryProfile, Measurements, MixAuthorityState
from runtime.charge.strategy import (
    CCMixExitConfig, CVMixExitConfig, ChargeRecipe, ChargeStrategy,
    MainPolicy, MainPolicyConfig, MainFallbackPolicy, MainFallbackPolicyConfig,
    MixPolicy, MixPolicyConfig, PlateauDetector, PlateauDetectorConfig,
    RecoveryPolicy, RecoveryPolicyConfig, StrategyRuntimeState,
)
from runtime.charge.profiles.recipe import factory_recipe


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

    def test_agm_recovery_exhausted_remains_main(self):
        state = StrategyRuntimeState()
        recovery = RecoveryPolicy(RecoveryPolicyConfig(4, 16.3, 1.0, exhausted_action="remain_main"))
        recovery.state.attempts = 4
        result = recovery.on_plateau(15.0, 1.0)
        self.assertEqual("main", result.next_stage)
        self.assertNotEqual("mix", result.next_stage)

    def test_main_fallback_is_chemistry_specific(self):
        fallback = MainFallbackPolicy(MainFallbackPolicyConfig(100.0, "AGM", 0.2, main_voltage=15.0, main_current=1.0))
        self.assertEqual("mix", fallback.evaluate(100.0, is_cv=True, current=0.2).next_stage)
        self.assertTrue(fallback.evaluate(100.0, is_cv=False, current=1.0).completed)

    def test_plateau_detector_separates_flat_cv_from_progress(self):
        detector = PlateauDetector(PlateauDetectorConfig(3, 0.05, 0.4, 0.05))
        flat = [Measurements(14.8, 0.6, 25.0, t) for t in (0.0, 1.0, 2.0)]
        progress = [Measurements(14.8, i, 25.0, t) for t, i in ((0.0, 0.8), (1.0, 0.6), (2.0, 0.4))]
        self.assertTrue(detector.is_plateau(flat, chemistry="EFB"))
        self.assertFalse(detector.is_plateau(progress, chemistry="EFB"))

    def test_mix_authority_exhaustion_stops_before_exit_logic(self):
        authority = MixAuthorityState(session_id="s1")
        mix = self.strategy.recipe.mix
        mix.authority = authority
        mix.config.cc  # config remains immutable and data-driven
        mix.evaluate("CC", Measurements(16.5, 2.0, 25.0, 0.0))
        result = mix.evaluate("CC", Measurements(16.5, 2.0, 25.0, 101.0))
        self.assertEqual("MIX_TIMEOUT", result.reason)
        self.assertTrue(result.completed)

    def test_charge_engine_uses_recipe_strategy_owner(self):
        engine = ChargeEngine(self.strategy.battery, strategy=self.strategy)
        result = engine.evaluate(StrategyRuntimeState(), Measurements(14.8, 5.0, 25.0, 0.0))
        self.assertEqual("main", result.next_stage)

    def test_mix_cc_vmax_delta_hold_exit(self):
        state = StrategyRuntimeState(stage="mix")
        self.strategy.evaluate(state, Measurements(16.5, 2.0, 25.0, 0.0), mix_mode="CC")
        self.strategy.evaluate(state, Measurements(16.47, 2.0, 25.0, 1.0), mix_mode="CC")
        result = self.strategy.evaluate(state, Measurements(16.46, 2.0, 25.0, 2.0), mix_mode="CC")
        self.assertEqual("MIX_CC_DELTA_CONFIRMED", result.reason)
        result = self.strategy.evaluate(state, Measurements(16.46, 2.0, 25.0, 12.0), mix_mode="CC")
        self.assertTrue(result.completed)

    def test_mix_cc_censors_only_explicitly_clipped_voltage_drop(self):
        mix = self.strategy.recipe.mix
        mix.evaluate("CC", Measurements(16.5, 2.0, 25.0, 0.0))
        clipped = mix.evaluate("CC", Measurements(16.46, 2.0, 25.0, 1.0), current_limit_clipped=True)
        self.assertEqual("MIX_CC_DELTA_CENSORED_CURRENT_LIMIT", clipped.reason)
        self.assertEqual("unarmed", mix.cc.state.phase)
        self.assertIsNone(mix.cc.state.observed_vmax)
        self.assertEqual(0, mix.cc.state.confirmation_count)
        self.assertEqual(
            "MIX_CC_WAIT_VMAX",
            mix.evaluate("CC", Measurements(16.46, 2.0, 25.0, 2.0)).reason,
        )
        self.assertEqual(
            "MIX_CC_VMAX_CONFIRMED",
            mix.evaluate("CC", Measurements(16.5, 2.0, 25.0, 3.0)).reason,
        )
        mix.evaluate("CC", Measurements(16.46, 2.0, 25.0, 4.0))
        result = mix.evaluate("CC", Measurements(16.46, 2.0, 25.0, 5.0))
        self.assertEqual("MIX_CC_DELTA_CONFIRMED", result.reason)

    def test_mix_cv_imin_delta_hold_exit(self):
        state = StrategyRuntimeState(stage="mix")
        self.strategy.evaluate(state, Measurements(16.5, 0.4, 25.0, 0.0), mix_mode="CV")
        self.strategy.evaluate(state, Measurements(16.5, 0.5, 25.0, 1.0), mix_mode="CV")
        result = self.strategy.evaluate(state, Measurements(16.5, 0.5, 25.0, 2.0), mix_mode="CV")
        self.assertEqual("MIX_CV_DELTA_CONFIRMED", result.reason)
        self.assertTrue(self.strategy.evaluate(state, Measurements(16.5, 0.5, 25.0, 12.0), mix_mode="CV").completed)

    def test_factory_mix_delta_needs_three_persistent_spaced_confirmations(self):
        recipe = factory_recipe("EFB").recipe.mix
        self.assertEqual(60.0, recipe.config.cc.confirmation_interval_seconds)
        self.assertEqual(60.0, recipe.config.cv.confirmation_interval_seconds)

        cc = recipe.cc
        cc.evaluate(Measurements(16.5, 2.0, 25.0, 0.0))  # establish Vmax
        for t in (1.0, 2.0, 30.0, 59.0):
            self.assertEqual("MIX_CC_DELTA_WAIT", cc.evaluate(Measurements(16.46, 2.0, 25.0, t)).reason)
        self.assertEqual(1, cc.state.confirmation_count)
        cc.evaluate(Measurements(16.5, 2.0, 25.0, 60.0))  # rebound breaks evidence
        self.assertEqual(0, cc.state.confirmation_count)
        cc.evaluate(Measurements(16.46, 2.0, 25.0, 61.0))
        self.assertEqual("MIX_CC_DELTA_WAIT", cc.evaluate(Measurements(16.46, 2.0, 25.0, 121.0)).reason)
        self.assertEqual("MIX_CC_DELTA_CONFIRMED", cc.evaluate(Measurements(16.46, 2.0, 25.0, 181.0)).reason)

        cv = recipe.cv
        cv.evaluate(Measurements(16.5, 0.3, 25.0, 0.0))  # establish Imin
        for t in (1.0, 2.0, 30.0, 59.0):
            self.assertEqual("MIX_CV_DELTA_WAIT", cv.evaluate(Measurements(16.5, 0.4, 25.0, t)).reason)
        self.assertEqual(1, cv.state.confirmation_count)
        cv.evaluate(Measurements(16.5, 0.3, 25.0, 60.0))  # current falls back
        self.assertEqual(0, cv.state.confirmation_count)
        cv.evaluate(Measurements(16.5, 0.4, 25.0, 61.0))
        self.assertEqual("MIX_CV_DELTA_WAIT", cv.evaluate(Measurements(16.5, 0.4, 25.0, 121.0)).reason)
        self.assertEqual("MIX_CV_DELTA_CONFIRMED", cv.evaluate(Measurements(16.5, 0.4, 25.0, 181.0)).reason)

    def test_mix_cv_current_containment_starts_after_mix_delay(self):
        cv = replace(self.strategy.recipe.mix.config.cv, hold_seconds=7200.0, confirmations_required=10)
        mix = MixPolicy(MixPolicyConfig(10000.0, self.strategy.recipe.mix.config.cc, cv))
        mix.evaluate("CV", Measurements(16.5, 0.4, 25.0, 0.0))
        mix.evaluate("CV", Measurements(16.5, 0.5, 25.0, 1.0))
        mix.evaluate("CV", Measurements(16.5, 0.5, 25.0, 2.0))

        before_delay = mix.evaluate("CV", Measurements(16.5, 0.8, 25.0, 1799.0))
        self.assertAlmostEqual(before_delay.target_current, 2.0)

        after_delay = mix.evaluate("CV", Measurements(16.5, 0.8, 25.0, 1800.0))
        self.assertAlmostEqual(after_delay.target_current, 0.9)

    def test_mix_cv_current_containment_does_not_follow_rising_current(self):
        cv = replace(self.strategy.recipe.mix.config.cv, hold_seconds=7200.0, confirmations_required=10)
        mix = MixPolicy(MixPolicyConfig(10000.0, self.strategy.recipe.mix.config.cc, cv))
        mix.evaluate("CV", Measurements(16.5, 0.4, 25.0, 0.0))
        mix.evaluate("CV", Measurements(16.5, 0.5, 25.0, 1.0))
        mix.evaluate("CV", Measurements(16.5, 0.5, 25.0, 2.0))

        first = mix.evaluate("CV", Measurements(16.5, 0.8, 25.0, 1800.0))
        later = mix.evaluate("CV", Measurements(16.5, 1.8, 25.0, 2400.0))
        self.assertAlmostEqual(first.target_current, 0.9)
        self.assertAlmostEqual(later.target_current, 0.9)

    def test_mix_cv_hold_preserves_existing_cap_and_timer_without_recalculation(self):
        cv = replace(self.strategy.recipe.mix.config.cv, hold_seconds=7200.0, confirmations_required=4)
        mix = MixPolicy(MixPolicyConfig(20000.0, self.strategy.recipe.mix.config.cc, cv))
        mix.evaluate("CV", Measurements(16.5, 0.4, 25.0, 0.0))
        mix.evaluate("CV", Measurements(16.5, 0.5, 25.0, 1.0))
        mix.evaluate("CV", Measurements(16.5, 0.5, 25.0, 2.0))
        mix.evaluate("CV", Measurements(16.5, 0.5, 25.0, 1800.0))
        state = mix.cv.state.containment
        state.fixed_limit = 0.7
        state.last_recalculation = 1800.0
        state.reduction_count = 3
        confirmed = mix.evaluate("CV", Measurements(16.5, 0.6, 25.0, 2400.0))
        self.assertEqual("MIX_CV_DELTA_CONFIRMED", confirmed.reason)
        self.assertEqual(2400.0, mix.cv.state.hold_started_at)
        self.assertEqual(0.7, confirmed.target_current)
        hold = mix.evaluate("CV", Measurements(16.5, 0.9, 25.0, 3600.0))
        self.assertEqual("MIX_CV_HOLD", hold.reason)
        self.assertEqual(0.7, hold.target_current)
        self.assertEqual((1800.0, 3), (state.last_recalculation, state.reduction_count))
        self.assertEqual(7200.0, cv.hold_seconds)
        complete = mix.evaluate("CV", Measurements(16.5, 0.9, 25.0, 9600.0))
        self.assertEqual("MIX_CV_HOLD_COMPLETE", complete.reason)
        self.assertTrue(complete.completed)
        self.assertEqual(0.7, complete.target_current)
        self.assertEqual((1800.0, 3), (state.last_recalculation, state.reduction_count))

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