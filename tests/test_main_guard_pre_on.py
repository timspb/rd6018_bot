"""Offline MAIN Guard pre-Output-ON admission; no hardware or app writes."""
import copy
from dataclasses import replace
import time
import unittest

from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.main_guard_session import attach_guard, read_guard
from runtime.charge.strategy.main_guard_pre_on import assess_main_guard_before_output_on


def canonical():
    return {
        "profile": "EFB", "stage": "Main Charge", "ah_limit": 60,
        "v2_trace_session_id": "sid", "v2_battery_id": "battery",
    }


def memory():
    return MainCurrentGuard.start(
        session_id="sid", battery_id="battery", segment_id="main-1",
        capacity_ah=60, recipe_initial_current_a=8,
    )


def live(current=6.0, ocp=6.1):
    state = {
        "output_state_code_v2": 0, "protection_code": 0,
        "set_current_readback_v2": current,
        "ocp_readback_v2": ocp,
    }
    state["_meta"] = {
        key: {"status": "ok", "age_s": 0.15}
        for key in ("output_state_code_v2", "protection_code",
                    "set_current_readback_v2", "ocp_readback_v2")
    }
    return state


class MainGuardPreOnTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.guard = memory()
        self.document = attach_guard(
            canonical(), self.guard, now_s=self.now, expected_revision=0,
        )
        self.live = live()

    def assess(self, **overrides):
        args = dict(
            session_document=self.document,
            restored_guard=self.guard, native_live=self.live,
            session_id="sid", battery_id="battery",
            profile="EFB", stage="Main Charge", target_current_a=6.0,
            owner_authorized=True, edge_lease_armed=True,
            now_epoch_s=self.now + 1.0,
        )
        args.update(overrides)
        return assess_main_guard_before_output_on(**args)

    def test_confirmed_journal_and_independent_off_programming(self):
        result = self.assess()
        self.assertEqual(result.status, "RECONCILED")
        self.assertTrue(result.guard_reconciled)
        self.assertEqual(result.journal_revision, 1)
        self.assertEqual(result.confirmed_ceiling_a, 6.0)

    def test_unguarded_profiles_remain_unaffected_by_this_optional_policy(self):
        doc = canonical()
        doc["profile"] = "AGM"
        result = self.assess(
            session_document=doc, restored_guard=None, profile="AGM",
        )
        self.assertEqual(result.status, "NOT_APPLICABLE")
        self.assertFalse(result.guard_reconciled)
        self.assertFalse(result.is_guarded)

    def test_missing_restored_guard_never_becomes_unrestricted(self):
        self.assertEqual(
            self.assess(restored_guard=None).reason,
            "guard_journal_was_not_restored",
        )
        self.assertEqual(
            self.assess(session_document=canonical()).reason,
            "in_memory_guard_has_no_canonical_journal",
        )

    def test_identity_profile_epoch_mismatch_rejected(self):
        for key, value in [
            ("session_id", "other"), ("battery_id", "other"),
            ("profile", "AGM"), ("stage", "Mix Mode"),
        ]:
            with self.subTest(key=key):
                result = self.assess(**{key: value})
                self.assertEqual(result.status, "BLOCKED")
        incompatible = replace(self.guard, segment_id="different-main-epoch")
        self.assertEqual(
            self.assess(restored_guard=incompatible).reason,
            "live_guard_and_canonical_journal_disagree",
        )

    def test_unresolved_pending_guard_blocks_restart(self):
        g, _ = self.guard.observe(
            now_s=0, output_on=True, measured_current_a=4, fresh=True
        )
        g, proposal = g.observe(
            now_s=1800, output_on=True, measured_current_a=4, fresh=True
        )
        self.assertIsNotNone(proposal)
        doc = attach_guard(canonical(), g, now_s=self.now, expected_revision=0)
        self.assertEqual(
            self.assess(session_document=doc, restored_guard=g).reason,
            "unresolved_pending_or_faulted_guard",
        )

    def test_tampered_guard_journal_blocks_output(self):
        doc = copy.deepcopy(self.document)
        doc["main_current_guard_v1"]["snapshot"]["hardware_limit_a"] = 12.0
        self.assertIn(
            "guard_checkpoint_not_trustworthy",
            self.assess(session_document=doc).reason,
        )

    def test_current_and_ocp_must_match_saved_ceiling(self):
        self.assertEqual(
            self.assess(target_current_a=7.0).reason,
            "restore_target_exceeds_saved_main_ceiling",
        )
        self.assertEqual(
            self.assess(native_live=live(7.0, 7.1)).reason,
            "physical_iset_exceeds_persisted_ceiling",
        )
        self.assertEqual(
            self.assess(native_live=live(5.0, 5.1)).reason,
            "physical_iset_does_not_match_resume_target",
        )
        self.assertEqual(
            self.assess(native_live=live(6.0, 7.0)).reason,
            "physical_ocp_not_confirmed",
        )

    def test_real_persisted_reduced_ceiling_never_reverts_to_initial(self):
        g = self.guard
        g, _ = g.observe(now_s=0, output_on=True, measured_current_a=4, fresh=True)
        g, pending = g.observe(now_s=1800, output_on=True,
                               measured_current_a=4, fresh=True)
        reduced = g.commit(
            proposal_id=pending.proposal_id, now_s=1801,
            measured_current_a=4, measured_current_fresh=True,
            current_limit_readback_a=5, current_readback_fresh=True,
            ocp_limit_a=5.1, ocp_readback_fresh=True,
        )
        doc = attach_guard(canonical(), reduced, now_s=self.now, expected_revision=0)
        restored, _ = read_guard(doc, session_id="sid",
                                 battery_id="battery", now_s=self.now+1)
        self.assertEqual(
            self.assess(session_document=doc, restored_guard=restored).reason,
            "restore_target_exceeds_saved_main_ceiling",
        )
        ok = self.assess(session_document=doc, restored_guard=restored,
                         target_current_a=5.0, native_live=live(5.0, 5.1))
        self.assertTrue(ok.guard_reconciled)
        self.assertEqual(ok.confirmed_ceiling_a, 5.0)

    def test_output_and_protection_registers_are_authoritative(self):
        for key, value, reason in (
            ("output_state_code_v2", 1, "output_not_independently_verified_off"),
            ("output_state_code_v2", None, "output_not_independently_verified_off"),
            ("protection_code", 2, "native_protection_not_normal"),
            ("protection_code", None, "native_protection_not_normal"),
        ):
            with self.subTest(key=key, value=value):
                snapshot = live()
                snapshot[key] = value
                self.assertEqual(
                    self.assess(native_live=snapshot).reason, reason,
                )

    def test_stale_missing_or_skewed_ha_heartbeat_rejected(self):
        for mutation in ("missing_meta", "stale", "skew", "unknown"):
            with self.subTest(mutation=mutation):
                snapshot = live()
                if mutation == "missing_meta":
                    del snapshot["_meta"]
                    expected = "native_freshness_metadata_missing"
                elif mutation == "stale":
                    snapshot["_meta"]["set_current_readback_v2"]["age_s"] = 55
                    expected = "native_sources_stale_or_skewed"
                elif mutation == "skew":
                    snapshot["_meta"]["ocp_readback_v2"]["age_s"] = 10
                    expected = "native_sources_stale_or_skewed"
                else:
                    snapshot["_meta"]["output_state_code_v2"]["status"] = "unavailable"
                    expected = "native_sources_stale_or_skewed"
                self.assertEqual(
                    self.assess(native_live=snapshot).reason, expected,
                )

    def test_owner_and_lease_must_be_independently_confirmed(self):
        for override in ({"edge_lease_armed": False},
                         {"owner_authorized": None}):
            with self.subTest(override=override):
                self.assertEqual(self.assess(**override).status, "BLOCKED")

    def test_never_assume_invalid_clock_or_nan_current_is_safe(self):
        self.assertEqual(
            self.assess(target_current_a=float("nan")).status, "BLOCKED",
        )
        self.assertEqual(
            self.assess(now_epoch_s=float("nan")).status, "BLOCKED",
        )


if __name__ == "__main__":
    unittest.main()
