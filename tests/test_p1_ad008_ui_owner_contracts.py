"""P1 AD008 path-specific contract evidence for three approved UI-only modules.

These functions are projections, not owners of journal persistence, elapsed
stage clocks, stage transitions, Output or future BW600 load execution.
"""
from __future__ import annotations

import unittest

from runtime.ui.components.journal_filter import (
    is_operator_journal_event, operator_journal_events, normalize_journal_events,
)
from runtime.ui.components.main_stage_progress import main_stage_countdown_status
from runtime.ui.components.mix_stage_progress import mix_finish_hold_status


class JournalProjectionContractTests(unittest.TestCase):
    @staticmethod
    def row(name: str) -> str:
        return f"2026-11-18 | INFO | MAIN | 14.2 | 1.0 | 25 | {name}"

    def test_service_rows_are_filtered_before_pagination(self):
        events = [
            self.row("CHECKPOINT data"),
            self.row("RESTORE service"),
            self.row("SESSION_PAUSE internal"),
            self.row("START | V2_START service"),
            self.row("OPERATOR_PAUSE"),
            self.row("CHARGE_STARTED"),
        ]
        visible = [self.row("OPERATOR_PAUSE"), self.row("CHARGE_STARTED")]
        self.assertEqual(operator_journal_events(events), visible)
        self.assertEqual(normalize_journal_events(events), visible)
        self.assertEqual(events[0], self.row("CHECKPOINT data"))

    def test_short_manual_log_line_stays_visible(self):
        self.assertTrue(is_operator_journal_event("human note"))
        self.assertFalse(is_operator_journal_event("  "))


class MainCountdownContractTests(unittest.TestCase):
    def view(self, **kwargs):
        params = dict(minimum_a=0.4, elapsed_s=3599,
                      clock_available=True, tail_ready=True,
                      hold_seconds=3600.0, intent="recovery", chemistry="EFB")
        params.update(kwargs)
        return main_stage_countdown_status(**params)

    def test_missing_clock_is_not_durable_hold_proof(self):
        self.assertIn("время минимума не подтверждено", self.view(clock_available=False))
        self.assertIn("время выдержки не подтверждено", self.view(hold_seconds=float("nan")))

    def test_ready_status_never_authorizes_transition(self):
        self.assertIn("выдержка выполнена, ожидаем решение",
                      self.view(elapsed_s=3600))
        self.assertIn("MAIN → MIX", self.view(elapsed_s=1))
        self.assertIn("решения по MAIN",
                      self.view(chemistry="AGM", elapsed_s=1))
        self.assertIn("ожидание устойчивого CV", self.view(tail_ready=False))


class MixHoldContractTests(unittest.TestCase):
    def view(self, **kwargs):
        params = dict(
            snapshot={"delta_reported": True, "finish_evidence": {
                "mode": "CV", "available": True,
                "reference_value": 0.4, "accepted_delta": 0.1,
            }},
            started_at=100.0, hold_seconds=600.0, now_s=101.0,
        )
        params.update(kwargs)
        return mix_finish_hold_status(**params)

    def test_mode_is_accepted_evidence_not_live_regulator(self):
        self.assertIn("ΔI подтверждена", self.view())
        cc = {"delta_reported": True, "finish_evidence": {
            "mode": "CC", "available": True,
            "reference_value": 14.2, "accepted_delta": 0.15,
        }}
        self.assertIn("ΔV подтверждена", self.view(snapshot=cc))

    def test_unconfirmed_evidence_cannot_be_reported_as_confirmed(self):
        self.assertIn("evidence недоступно", self.view(snapshot={}))
        self.assertIn("время не подтверждено", self.view(started_at=999.0))
        self.assertIn("время не подтверждено", self.view(hold_seconds=0))

    def test_elapsed_hold_is_only_a_display(self):
        self.assertIn("0ч 00м", self.view(now_s=999.0))
        self.assertIn("SAFE_WAIT", self.view(now_s=999.0))


if __name__ == "__main__":
    unittest.main()
