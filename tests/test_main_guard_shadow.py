import ast
from pathlib import Path
import unittest

from runtime.charge.strategy.main_guard_shadow import MainGuardShadow


class MainGuardShadowTests(unittest.TestCase):
    def sample(self, holder, t, **kw):
        args = dict(session_id="accepted", battery_id="bat", chemistry="EFB",
                    capacity_ah=72, recipe_current_a=8, stage="MAIN",
                    output_on=True, output_current_a=4, fresh=True)
        args.update(kw)
        return holder.observe(now_s=t, **args)

    def test_proposes_after_30_minutes_with_current_plus_one(self):
        h = MainGuardShadow()
        self.sample(h, 0)
        for t in range(30, 1801, 30):
            proposal = self.sample(h, t)
        self.assertEqual(proposal.target_limit_a, 5)

    def test_gap_stale_cooling_off_and_stage_transition_do_not_accrue(self):
        for changes in ({"fresh": False}, {"stage": "COOLING"},
                        {"output_on": False}, {"output_on": None}):
            h = MainGuardShadow()
            self.sample(h, 0)
            self.sample(h, 30, **changes)
            self.sample(h, 1800)
            self.assertEqual(h.guard.accrued_output_on_s, 0)
        h = MainGuardShadow()
        self.sample(h, 0)
        self.sample(h, 91)
        self.assertEqual(h.guard.accrued_output_on_s, 0)

    def test_short_cooling_or_unknown_output_breaks_main_continuity(self):
        for bad in ({"stage": "COOLING"}, {"output_on": None}):
            with self.subTest(bad=bad):
                h = MainGuardShadow()
                self.sample(h, 0)
                self.sample(h, 30)
                self.assertEqual(h.guard.accrued_output_on_s, 30)
                self.sample(h, 60, **bad)
                self.sample(h, 90)
                self.assertEqual(h.guard.accrued_output_on_s, 30)
                self.sample(h, 120)
                self.assertEqual(h.guard.accrued_output_on_s, 60)

    def test_wrong_chemistry_never_starts_guard(self):
        h = MainGuardShadow()
        self.sample(h, 0, chemistry="AGM")
        self.assertIsNone(h.guard)

    def test_pending_proposal_is_not_disclosed_outside_exact_main_context(self):
        h = MainGuardShadow()
        self.sample(h, 0)
        for t in range(30, 1801, 30):
            pending = self.sample(h, t)
        self.assertIsNotNone(pending)
        cap = h.guard.hardware_limit_a
        for changes in (
            {"chemistry": "AGM"},
            {"chemistry": "UNKNOWN"},
            {"stage": "COOLING"},
            {"session_id": "another-session"},
            {"battery_id": "another-battery"},
            {"session_id": None},
            {"output_on": None},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(self.sample(h, 1802, **changes))
                self.assertEqual(h.guard.hardware_limit_a, cap)
        self.assertEqual(h.guard.pending, pending)

    def test_pending_expiry_revokes_stale_proposal_not_current_ceiling(self):
        h = MainGuardShadow()
        self.sample(h, 0)
        for t in range(30, 1801, 30):
            pending = self.sample(h, t)
        self.assertIsNotNone(pending)
        self.assertIsNone(self.sample(h, 2000))
        self.assertIsNone(h.proposal)
        self.assertIsNone(h.guard.pending)
        self.assertEqual(h.guard.fault, "proposal_ack_timeout")
        self.assertEqual(h.guard.hardware_limit_a, 7.2)

    def test_false_string_freshness_cannot_accrue_main_time(self):
        h = MainGuardShadow()
        self.sample(h, 0)
        self.assertIsNone(self.sample(h, 30, fresh="false"))
        self.assertEqual(h.guard.accrued_output_on_s, 0)
        self.assertIsNone(self.sample(h, 60))
        self.assertEqual(h.guard.accrued_output_on_s, 0)
        self.assertIsNone(h.proposal)

    def test_malformed_current_sample_faults_shadow_without_leaking_proposal(self):
        h = MainGuardShadow()
        self.sample(h, 0)
        self.assertIsNone(self.sample(h, 30, output_current_a="not-a-current"))
        self.assertEqual(h.guard.fault, "untrusted_main_current_sample")
        self.assertIsNone(h.proposal)
        self.assertIsNone(self.sample(h, 60))
        self.assertEqual(h.guard.hardware_limit_a, 7.2)

    def test_restart_keeps_pending_proposal(self):
        h = MainGuardShadow()
        self.sample(h, 0)
        for t in range(30, 1801, 30):
            proposal = self.sample(h, t)
        restored = MainGuardShadow.restore(
            h.guard.snapshot(), session_id="accepted", battery_id="bat", now_s=1801
        )
        self.assertEqual(restored.proposal, proposal)

    def test_missing_identity_noop_and_no_default_persistence(self):
        h = MainGuardShadow()
        writes = []
        self.sample(h, 0, session_id=None, owner_allows_persistence=True,
                    persistence=writes.append)
        self.assertIsNone(h.guard)
        self.sample(h, 0)
        self.assertEqual(writes, [])

    def test_logger_observer_is_inside_the_existing_execution_lock(self):
        path = Path(__file__).resolve().parents[1] / "runtime" / "production_runtime.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        logger = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.AsyncFunctionDef) and n.name == "data_logger")
        found = False
        for node in ast.walk(logger):
            if not isinstance(node, ast.AsyncWith):
                continue
            if not any("_guard_owner_lock" in ast.unparse(i.context_expr) for i in node.items):
                continue
            calls = [ast.unparse(c.func) for s in node.body for c in ast.walk(s)
                     if isinstance(c, ast.Call)]
            if "_main_guard_shadow.observe" in calls and "charge_controller.tick" in calls:
                found = True
        self.assertTrue(found)
        source = path.read_text(encoding="utf-8")
        self.assertIn('("output_state_code_v2", "current")', source)
        self.assertIn("telemetry_freshness(", source)
        self.assertNotIn("execute_main_current_guard_reduction(", source)


if __name__ == "__main__":
    unittest.main()
