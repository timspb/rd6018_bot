import copy
import unittest

from runtime.charge.strategy.main_current_guard import (
    ACK_TIMEOUT_S, HARDWARE_CURRENT_FLOOR_A, MainCurrentGuard, GuardError,
)


class MainCurrentGuardTests(unittest.TestCase):
    def make(self, capacity=72, recipe=20, **kw):
        return MainCurrentGuard.start(session_id="s1", battery_id="b1", segment_id="main-1",
                                      capacity_ah=capacity, recipe_initial_current_a=recipe, **kw)

    def due(self, state, current=4.0):
        start = state.last_observed_at_s if state.last_observed_at_s is not None else 0
        proposal = None
        for step in range(61):
            state, proposal = state.observe(
                now_s=start + 30 * step, output_on=True,
                measured_current_a=current, fresh=True)
            if proposal is not None:
                break
        return state, proposal

    def ack(self, state, proposal, now=1801, *, current=4, ocp=None, fresh=True,
            current_readback_fresh=True, ocp_fresh=True):
        return state.commit(proposal_id=proposal.proposal_id, now_s=now, measured_current_a=current,
                            measured_current_fresh=fresh, ocp_limit_a=(proposal.target_limit_a + 0.1) if ocp is None else ocp,
                            current_limit_readback_a=proposal.target_limit_a,
                            current_readback_fresh=current_readback_fresh, ocp_readback_fresh=ocp_fresh)

    def test_72ah_starts_at_7_2a(self):
        self.assertEqual(self.make().initial_limit_a, 7.2)

    def test_capacity_extremes_and_recipe_ceiling(self):
        self.assertEqual(self.make(capacity=240).initial_limit_a, 12)
        self.assertEqual(self.make(capacity=20, recipe=8).initial_limit_a, 2)

    def test_rejects_below_hardware_floor(self):
        with self.assertRaises(GuardError):
            self.make(capacity=.5)

    def test_no_proposal_before_1800s_on_time(self):
        state, p = self.due(self.make(), current=6.2)
        self.assertIsNone(p)
        self.assertEqual(state.hardware_limit_a, 7.2)

    def test_proposes_after_1800s_and_uses_current_plus_one(self):
        state, p = self.due(self.make(), current=4)
        self.assertEqual(p.target_limit_a, 5)
        self.assertEqual(state.hardware_limit_a, 7.2)

    def test_long_gap_cannot_be_counted_as_3600s_main(self):
        s = self.make()
        s, _ = s.observe(now_s=0, output_on=True, measured_current_a=4, fresh=True)
        s, p = s.observe(now_s=3600, output_on=True, measured_current_a=4, fresh=True)
        self.assertIsNone(p)
        self.assertEqual(s.accrued_output_on_s, 0)
        self.assertEqual(s.hardware_limit_a, 7.2)
        for ts in range(3630, 5401, 30):
            s, p = s.observe(now_s=ts, output_on=True, measured_current_a=4, fresh=True)
        self.assertIsNotNone(p)
        self.assertEqual(p.target_limit_a, 5)
        s, again = s.observe(now_s=5410, output_on=True, measured_current_a=3, fresh=True)
        self.assertIsNone(again)
        self.assertEqual(s.pending, p)

    def test_90_second_bounded_gap_counts_but_91_seconds_does_not(self):
        bounded, _ = self.make().observe(now_s=0, output_on=True, measured_current_a=4, fresh=True)
        bounded, _ = bounded.observe(now_s=90, output_on=True, measured_current_a=4, fresh=True)
        self.assertEqual(bounded.accrued_output_on_s, 90)
        unbounded, _ = self.make().observe(now_s=0, output_on=True, measured_current_a=4, fresh=True)
        unbounded, _ = unbounded.observe(now_s=91, output_on=True, measured_current_a=4, fresh=True)
        self.assertEqual(unbounded.accrued_output_on_s, 0)

    def test_rising_current_cannot_raise_limit(self):
        s, p = self.due(self.make(), current=4)
        s = self.ack(s, p)
        s, p2 = self.due(s, current=9)
        self.assertIsNone(p2)
        self.assertEqual(s.hardware_limit_a, 5)

    def test_repeated_samples_do_not_double_count_elapsed_interval(self):
        s = self.make()
        p = None
        for ts in range(0, 1801, 30):
            s, p = s.observe(now_s=ts, output_on=True, measured_current_a=4, fresh=True)
            if ts == 300:
                s, duplicate = s.observe(
                    now_s=ts, output_on=True, measured_current_a=4, fresh=True)
                self.assertIsNone(duplicate)
        self.assertIsNotNone(p)

    def test_cooling_off_pauses_accrual(self):
        s = self.make()
        for ts in range(0, 901, 30):
            s, _ = s.observe(now_s=ts, output_on=True, measured_current_a=4, fresh=True)
        s, _ = s.observe(now_s=5000, output_on=False, measured_current_a=None, fresh=False)
        s, _ = s.observe(now_s=9000, output_on=True, measured_current_a=4, fresh=True)
        self.assertEqual(s.accrued_output_on_s, 900)

    def test_agm_stage_change_preserves_cap_and_elapsed(self):
        s = self.make()
        for ts in range(0, 601, 30):
            s, _ = s.observe(now_s=ts, output_on=True, measured_current_a=4, fresh=True, stage="MAIN")
        self.assertEqual(s.hardware_limit_a, 7.2)
        self.assertEqual(s.accrued_output_on_s, 600)

    def test_intermediate_desulfation_live_time_never_counts_as_main(self):
        s = self.make()
        for ts in range(0, 301, 30):
            s, _ = s.observe(now_s=ts, output_on=True, measured_current_a=3, fresh=True)
        s, _ = s.observe(now_s=3600, output_on=True, measured_current_a=3,
                         fresh=True, stage="DESULFATION")
        s, _ = s.observe(now_s=3800, output_on=True, measured_current_a=3,
                         fresh=True, stage="MAIN")
        self.assertEqual(s.accrued_output_on_s, 300)
        for ts in range(3830, 5301, 30):
            s, p = s.observe(now_s=ts, output_on=True, measured_current_a=3,
                             fresh=True, stage="MAIN")
        self.assertIsNotNone(p)

    def test_bogus_output_on_or_fresh_types_do_not_accrue(self):
        s, _ = self.make().observe(now_s=0, output_on="off",
                                    measured_current_a=3, fresh=True)
        self.assertEqual(s.fault, "untrusted_output_or_freshness_type")

    def test_remaining_main_deadline_is_consistent(self):
        s = self.make()
        for ts in range(0, 401, 20):
            s, _ = s.observe(now_s=ts, output_on=True, measured_current_a=3, fresh=True)
        self.assertEqual(s.next_deadline_s, 1400)

    def test_only_explicit_desulf_return_resets_segment_limit(self):
        s, p = self.due(self.make(), current=4)
        s = self.ack(s, p)
        s, _ = s.observe(now_s=2000, output_on=False, measured_current_a=None, fresh=False, stage="DESULFATION")
        s = s.return_after_verified_desulfation(
            now_s=2100, from_stage="DESULFATION", to_stage="MAIN",
            output_off_proven=True, current_readback_a=7.2,
            ocp_readback_a=7.3, readbacks_fresh=True, segment_id="main-return-2")
        self.assertEqual(s.hardware_limit_a, 7.2)
        self.assertEqual(s.accrued_output_on_s, 0)
        self.assertIn("return", s.segment_id)

    def test_desulfation_return_must_have_verified_i_and_ocp(self):
        s, p = self.due(self.make(), current=4)
        s = self.ack(s, p)
        bad = s.return_after_verified_desulfation(
            now_s=2100, from_stage="DESULFATION", to_stage="MAIN",
            output_off_proven=True, current_readback_a=5.0,
            ocp_readback_a=5.1, readbacks_fresh=True, segment_id="return-2")
        self.assertEqual(bad.hardware_limit_a, 5)
        self.assertEqual(bad.fault, "desulfation_return_readback_mismatch")
        good = s.return_after_verified_desulfation(
            now_s=2100, from_stage="DESULFATION", to_stage="MAIN",
            output_off_proven=True, current_readback_a=7.2,
            ocp_readback_a=7.3, readbacks_fresh=True, segment_id="return-2")
        self.assertEqual(good.hardware_limit_a, 7.2)
        self.assertEqual(good.accrued_output_on_s, 0)
        self.assertFalse(good.last_output_on)

    def test_desulfation_return_without_off_proof_is_rejected(self):
        s, p = self.due(self.make(), current=4)
        s = self.ack(s, p)
        unproved = s.return_after_verified_desulfation(
            now_s=2100, from_stage="DESULFATION", to_stage="MAIN",
            output_off_proven=False, current_readback_a=7.2,
            ocp_readback_a=7.3, readbacks_fresh=True, segment_id="return-2")
        self.assertIsNotNone(unproved.fault)
        self.assertEqual(unproved.hardware_limit_a, 5)

    def test_missing_ocp_headroom_is_not_accepted_as_commit(self):
        s, p = self.due(self.make(), current=4)
        bad = self.ack(s, p, ocp=p.target_limit_a)
        self.assertEqual(bad.fault, "OCP_readback_mismatch")
        self.assertEqual(bad.hardware_limit_a, 7.2)

    def test_wrong_i_readback_does_not_commit(self):
        s, p = self.due(self.make(), current=4)
        bad = s.commit(
            proposal_id=p.proposal_id, now_s=1801, measured_current_a=4,
            measured_current_fresh=True, current_limit_readback_a=7.2,
            current_readback_fresh=True, ocp_limit_a=5.1, ocp_readback_fresh=True)
        self.assertEqual(bad.fault, "programmed_current_readback_mismatch")

    def test_stage_change_alone_does_not_reset_cap(self):
        s, p = self.due(self.make(), current=4)
        s = self.ack(s, p)
        s, _ = s.observe(now_s=2000, output_on=True, measured_current_a=4, fresh=True, stage="DESULFATION")
        s, _ = s.observe(now_s=2200, output_on=True, measured_current_a=4, fresh=True, stage="MAIN")
        self.assertEqual(s.hardware_limit_a, 5)

    def test_missing_or_stale_telemetry_never_lowers(self):
        s, _ = self.make().observe(now_s=0, output_on=True, measured_current_a=None, fresh=False)
        s, p = s.observe(now_s=1800, output_on=True, measured_current_a=None, fresh=False)
        self.assertIsNone(p)
        self.assertEqual(s.hardware_limit_a, 7.2)
        self.assertEqual(s.accrued_output_on_s, 0)

    def test_stale_midpoint_breaks_active_main_time_accounting(self):
        s = self.make()
        for ts in range(0, 601, 30):
            s, _ = s.observe(now_s=ts, output_on=True, measured_current_a=4, fresh=True)
        s, _ = s.observe(now_s=900, output_on=True, measured_current_a=4, fresh=False)
        self.assertEqual(s.accrued_output_on_s, 600)
        self.assertFalse(s.last_output_on)
        s, p = s.observe(now_s=1800, output_on=True, measured_current_a=4, fresh=True)
        self.assertIsNone(p)
        self.assertEqual(s.accrued_output_on_s, 600)
        for ts in range(1830, 3001, 30):
            s, p = s.observe(now_s=ts, output_on=True, measured_current_a=4, fresh=True)
        self.assertIsNotNone(p)
        self.assertEqual(p.target_limit_a, 5)

    def test_missing_current_breaks_accounting_even_with_fresh_output(self):
        s = self.make()
        for ts in range(0, 301, 30):
            s, _ = s.observe(now_s=ts, output_on=True, measured_current_a=4, fresh=True)
        s, _ = s.observe(now_s=600, output_on=True, measured_current_a=None, fresh=True)
        self.assertEqual(s.accrued_output_on_s, 300)
        self.assertFalse(s.last_output_on)
        s, p = s.observe(now_s=1800, output_on=True, measured_current_a=4, fresh=True)
        self.assertIsNone(p)
        self.assertEqual(s.accrued_output_on_s, 300)

    def test_zero_amp_samples_do_not_record_main_time_or_propose_a_ratchet(self):
        s = self.make()
        proposal = None
        for ts in range(0, 3601, 30):
            s, proposal = s.observe(
                now_s=ts, output_on=True, measured_current_a=0.0,
                fresh=True, stage="MAIN",
            )
            self.assertIsNone(proposal)
        self.assertEqual(s.accrued_output_on_s, 0)
        self.assertEqual(s.hardware_limit_a, 7.2)

    def test_fault_fails_closed_and_sticks(self):
        s, _ = self.make().observe(now_s=1, output_on=True, measured_current_a=4, fresh=True, fault="thermal")
        self.assertEqual(s.fault, "external_fault:thermal")
        self.assertEqual(s.observe(now_s=2, output_on=True, measured_current_a=2, fresh=True)[0], s)

    def test_ambiguous_bogus_and_low_readbacks_fail_closed(self):
        s, p = self.due(self.make(), current=4)
        self.assertIn("ambiguous", s.commit(proposal_id="bogus", now_s=1801, measured_current_a=4,
                       measured_current_fresh=True, current_limit_readback_a=5, current_readback_fresh=True,
                       ocp_limit_a=7.2, ocp_readback_fresh=True).fault)
        self.assertIn("readback", self.ack(s, p, ocp=0.1).fault)
        self.assertIn("readback_mismatch", self.ack(s, p, ocp=8).fault)

    def test_stale_current_or_ocp_ack_fails(self):
        s, p = self.due(self.make(), current=4)
        self.assertEqual(self.ack(s, p, fresh=False).fault, "stale_readback")
        self.assertEqual(self.ack(s, p, current_readback_fresh=False).fault, "stale_readback")
        self.assertEqual(self.ack(s, p, ocp_fresh=False).fault, "stale_readback")

    def test_commit_requires_fresh_current_and_ocp_readback(self):
        s, p = self.due(self.make(), current=4)
        s = self.ack(s, p)
        self.assertEqual(s.hardware_limit_a, 5)
        self.assertIsNone(s.pending)

    def test_ack_timeout_fails_closed(self):
        s, _ = self.due(self.make(), current=4)
        s, _ = s.observe(now_s=1800 + ACK_TIMEOUT_S + 1, output_on=True, measured_current_a=4, fresh=True)
        self.assertEqual(s.fault, "proposal_ack_timeout")

    def test_ack_cannot_move_observation_clock_backward(self):
        s, proposal = self.due(self.make(), current=4)
        s, _ = s.observe(now_s=1850, output_on=True, measured_current_a=4, fresh=True)
        self.assertEqual(s.last_observed_at_s, 1850)
        rolled_back = self.ack(s, proposal, now=1801)
        self.assertEqual(rolled_back.fault, "proposal_ack_timeout_or_clock_rollback")
        self.assertEqual(rolled_back.hardware_limit_a, 7.2)

    def test_replay_wrong_proposal_id_fails_closed(self):
        s, p = self.due(self.make(), current=4)
        s = self.ack(s, p)
        replay = s.commit(proposal_id=p.proposal_id, now_s=1802, measured_current_a=4,
                          measured_current_fresh=True, current_limit_readback_a=5, current_readback_fresh=True,
                          ocp_limit_a=5, ocp_readback_fresh=True)
        self.assertIn("ambiguous", replay.fault)

    def test_snapshot_restart_preserves_cap_and_session_state(self):
        s, p = self.due(self.make(), current=4)
        s = self.ack(s, p)
        restored = MainCurrentGuard.restore(s.snapshot(), session_id="s1", battery_id="b1", now_s=1802)
        self.assertEqual(restored.hardware_limit_a, 5)
        self.assertEqual(restored.segment_id, s.segment_id)

    def test_journal_schema_and_identity_mismatch_rejected(self):
        snap = self.make().snapshot()
        with self.assertRaises(GuardError):
            MainCurrentGuard.restore(snap, session_id="other", battery_id="b1", now_s=1)
        bad = copy.deepcopy(snap); bad["schema_version"] = 99
        with self.assertRaises(GuardError):
            MainCurrentGuard.restore(bad, session_id="s1", battery_id="b1", now_s=1)

    def test_battery_identity_cannot_change_during_observation(self):
        s, _ = self.make().observe(now_s=1, output_on=True, measured_current_a=4, fresh=True, battery_id="b2")
        self.assertEqual(s.fault, "battery_identity_changed")

    def test_restore_rejects_clock_rollback_and_bounds_tampering(self):
        snap = self.make(now_s=100).snapshot()
        with self.assertRaises(GuardError):
            MainCurrentGuard.restore(snap, session_id="s1", battery_id="b1", now_s=99)
        bad = copy.deepcopy(snap); bad["hardware_limit_a"] = 13
        with self.assertRaises(GuardError):
            MainCurrentGuard.restore(bad, session_id="s1", battery_id="b1", now_s=101)

    def test_pending_proposal_is_durable(self):
        s, p = self.due(self.make(), current=4)
        restored = MainCurrentGuard.restore(s.snapshot(), session_id="s1", battery_id="b1", now_s=1801)
        self.assertEqual(restored.pending, p)
        self.assertEqual(restored.hardware_limit_a, 7.2)

    def test_no_cross_session_restore(self):
        with self.assertRaises(GuardError):
            MainCurrentGuard.restore(self.make().snapshot(), session_id="s2", battery_id="b1", now_s=1)

    def test_next_deadline_reports_interval_or_ack_deadline(self):
        s, p = self.due(self.make(), current=4)
        self.assertEqual(s.next_deadline_s, p.deadline_s)
        self.assertEqual(self.make().next_deadline_s, 1800)


if __name__ == "__main__":
    unittest.main()