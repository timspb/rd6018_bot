from __future__ import annotations

import unittest
from unittest.mock import patch

import physical_test_control_d062
import rd_managed_mix
import rd_managed_mix_adoption
from ha_history import ContinuousOnEvidence, MixHistoryEvidence
from runtime.charge.evidence import adopted_mix_prior_age as owner
from runtime.safety.runtime_guard import RuntimeSafetyError


def evidence(elapsed, fetched, *, reliable=True):
    return MixHistoryEvidence(
        fetched_at_s=fetched,
        output=ContinuousOnEvidence(reliable, None, elapsed, "fixture"),
    )


class AdoptedMixPriorAgeTests(unittest.TestCase):
    def test_public_compatibility_names_are_same_objects_for_all_callers(self):
        self.assertIs(rd_managed_mix.PriorMixAge, owner.PriorMixAge)
        self.assertIs(rd_managed_mix.PriorMixAgeSource, owner.PriorMixAgeSource)
        self.assertIs(rd_managed_mix_adoption.PriorMixAge, owner.PriorMixAge)
        self.assertIs(rd_managed_mix_adoption.PriorMixAgeSource, owner.PriorMixAgeSource)
        self.assertIs(rd_managed_mix_adoption.resolve_prior_mix_age, owner.resolve_prior_mix_age)
        self.assertIs(physical_test_control_d062.resolve_prior_mix_age, owner.resolve_prior_mix_age)

    def test_elapsed_projects_forward_and_never_backwards(self):
        self.assertEqual(owner.aged_elapsed(40, 100, 125), 65)
        self.assertEqual(owner.aged_elapsed(40, 125, 100), 40)

    def test_recorder_and_operator_selection_and_tie_precedence(self):
        recorder = evidence(100, 900)
        operator = owner.resolve_prior_mix_age(
            recorder, declared_elapsed_s=110, declared_at_s=900, now_s=900
        )
        self.assertEqual(operator.source, owner.PriorMixAgeSource.OPERATOR_DECLARED)
        tie = owner.resolve_prior_mix_age(
            recorder, declared_elapsed_s=100, declared_at_s=900, now_s=900
        )
        self.assertEqual(tie.source, owner.PriorMixAgeSource.RECORDER)

    def test_declared_elapsed_and_observed_defaults_and_time_default(self):
        with patch.object(owner.time, "time", return_value=1000):
            by_default = owner.resolve_prior_mix_age(
                None, declared_elapsed_s=12, declared_at_s=990
            )
        self.assertEqual(by_default.elapsed_s, 22)
        self.assertEqual(by_default.observed_at_s, 1000)
        no_observed = owner.resolve_prior_mix_age(None, declared_elapsed_s=12, now_s=1000)
        self.assertEqual(no_observed.elapsed_s, 12)

    def test_unreliable_or_absent_recorder_requires_operator_evidence(self):
        for item in (None, evidence(500, 900, reliable=False), evidence(None, 900)):
            with self.subTest(item=item):
                with self.assertRaisesRegex(RuntimeSafetyError, "prior external Mix age is not proven"):
                    owner.resolve_prior_mix_age(item, now_s=900)

    def test_fresh_recorder_must_be_strictly_greater_than_aged_floor(self):
        floor = owner.age_prior_mix_age(
            owner.PriorMixAge(100, owner.PriorMixAgeSource.OPERATOR_DECLARED, 900), now_s=910
        )
        self.assertEqual(floor.elapsed_s, 110)
        self.assertIs(owner.select_fresh_recorder_age(floor, evidence(99, 900), now_s=910), floor)
        self.assertIs(owner.select_fresh_recorder_age(floor, evidence(100, 900), now_s=910), floor)
        above = owner.select_fresh_recorder_age(floor, evidence(111, 900), now_s=910)
        self.assertEqual(above.elapsed_s, 121)
        self.assertEqual(above.source, owner.PriorMixAgeSource.RECORDER)

    def test_unreliable_or_absent_fresh_history_preserves_floor(self):
        floor = owner.PriorMixAge(20, owner.PriorMixAgeSource.OPERATOR_DECLARED, 100)
        self.assertEqual(owner.select_fresh_recorder_age(floor, None, now_s=100), floor)
        self.assertEqual(
            owner.select_fresh_recorder_age(floor, evidence(500, 100, reliable=False), now_s=100), floor
        )

    def test_invalid_elapsed_and_timestamps_keep_established_errors(self):
        for elapsed in (-1, float("nan"), float("inf")):
            with self.subTest(elapsed=elapsed):
                with self.assertRaisesRegex(RuntimeSafetyError, "prior Mix age is invalid"):
                    owner.aged_elapsed(elapsed, 0, 0)
        for timestamp in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(RuntimeSafetyError, "prior Mix age timestamp is invalid"):
                    owner.aged_elapsed(1, timestamp, 0)
                with self.assertRaisesRegex(RuntimeSafetyError, "prior Mix age timestamp is invalid"):
                    owner.aged_elapsed(1, 0, timestamp)
        with self.assertRaisesRegex(RuntimeSafetyError, "prior Mix age is required"):
            owner.aged_elapsed(None, 0, 0)


if __name__ == "__main__":
    unittest.main()
