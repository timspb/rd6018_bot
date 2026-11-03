"""Parity of production native-recipe recovery/MIX target and timing policies."""
import unittest

from runtime.charge.programs.native_recipe_catalog import native_recipes
from runtime.charge.programs.native_recipe_policy import native_policy
from runtime.charge.strategy.desulfation import (
    decide_desulfation, desulfation_duration_seconds, select_desulfation_target,
)
from runtime.charge.strategy.mix import select_mix_target


class NativeRecipeTargetParityTests(unittest.TestCase):
    def test_recovery_and_mix_targets_match_canonical_for_all_profiles(self):
        for entry in native_recipes():
            policy = native_policy(entry.recipe_id)
            for capacity in (1.0, 45.0, 72.0, 120.0, 250.0):
                with self.subTest(recipe=entry.recipe_id, capacity=capacity):
                    self.assertEqual(
                        policy.desulfation_target(capacity_ah=capacity),
                        select_desulfation_target(capacity_ah=capacity),
                    )
                    self.assertEqual(
                        policy.mix_target(capacity_ah=capacity),
                        select_mix_target(profile=entry.profile,
                                          capacity_ah=capacity),
                    )

    def test_recovery_transition_matches_existing_time_boundary(self):
        cutoff = desulfation_duration_seconds()
        for entry in native_recipes():
            policy = native_policy(entry.recipe_id)
            for seconds in (0., 1., cutoff - 1., cutoff, cutoff + 1.):
                with self.subTest(recipe=entry.recipe_id, seconds=seconds):
                    self.assertEqual(
                        policy.desulfation_decision(active_elapsed_s=seconds),
                        decide_desulfation(active_elapsed_s=seconds),
                    )
