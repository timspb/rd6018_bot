"""Post-tick journal ownership and cadence contracts."""
import unittest

from runtime.charge.evidence.charge_cycle_journal import record_charge_cycle_journal


class ChargeCycleJournalTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def invoke(self, **overrides):
        options = dict(
            previous_stage="MAIN",
            current_stage="MIX",
            actions={
                "log_event_end": {
                    "stage": "MAIN", "v": 14.4, "i": 1.2, "t": 25.0,
                    "ah": 2.0, "time_sec": 90, "ah_on_stage": 0.5,
                    "trigger": "confirmed_delta",
                },
                "log_event_sub": "MAIN_FINISHED",
                "log_event": "STAGE_COMPLETE",
            },
            charge_active=True,
            last_checkpoint_time=100.0,
            now_s=700.0,
            voltage_v=15.0,
            current_a=0.8,
            temperature_c=25.0,
            ah=2.5,
            live={},
            signal=None,
            session_id="session-1",
            hold_started_at=None,
            mix_stage="MIX",
            max_age_s=300.0,
            log_event=lambda *args: self.calls.append(("event", *args)),
            log_stage_end=lambda *args: self.calls.append(("end", *args)),
            log_checkpoint=lambda *args: self.calls.append(("checkpoint", *args)),
            warn=lambda *args: self.calls.append(("warning", *args)),
        )
        options.update(overrides)
        return record_charge_cycle_journal(**options)

    def test_preserves_post_tick_event_order_then_checkpoint_and_mix_progress(self):
        result = self.invoke()
        self.assertEqual(result, 700.0)
        self.assertEqual(
            [call[0] for call in self.calls],
            ["event", "end", "event", "event", "checkpoint", "event"],
        )
        self.assertIn("STAGE_CHANGE | MAIN -> MIX", self.calls[0][-1])
        self.assertEqual(self.calls[1][0:2], ("end", "MAIN"))
        self.assertEqual(self.calls[2][-1], "MAIN_FINISHED")
        self.assertEqual(self.calls[3][-1], "STAGE_COMPLETE")
        self.assertIn("MIX_PROGRESS | evidence=unavailable", self.calls[-1][-1])

    def test_existing_600_second_boundary_and_inactive_behavior(self):
        unchanged = self.invoke(previous_stage="MIX", last_checkpoint_time=101.0,
                                now_s=700.0, actions={})
        self.assertEqual(unchanged, 101.0)
        self.assertEqual(self.calls, [])
        due = self.invoke(previous_stage="MIX", last_checkpoint_time=100.0,
                          now_s=700.0, actions={})
        self.assertEqual(due, 700.0)
        self.assertEqual(self.calls[0][0], "checkpoint")
        self.calls.clear()
        inactive = self.invoke(previous_stage="MIX", charge_active=False,
                               last_checkpoint_time=0.0, now_s=700.0, actions={})
        self.assertEqual(inactive, 0.0)
        self.assertEqual(self.calls, [])

    def test_emergency_unavailable_suppression_uses_existing_600_second_window(self):
        actions = {"log_event": "EMERGENCY_UNAVAILABLE"}
        self.invoke(previous_stage="MIX", actions=actions, charge_active=False,
                    last_checkpoint_time=700.0, now_s=1000.0)
        self.assertEqual([call[-1] for call in self.calls if call[0] == "event"],
                         ["EMERGENCY_UNAVAILABLE"])
        self.calls.clear()
        self.invoke(previous_stage="MIX", actions=actions, charge_active=False,
                    last_checkpoint_time=700.0, now_s=1599.0)
        self.assertEqual(self.calls, [])
        self.invoke(previous_stage="MIX", actions=actions, charge_active=False,
                    last_checkpoint_time=700.0, now_s=1600.0)
        self.assertEqual([call[-1] for call in self.calls if call[0] == "event"],
                         ["EMERGENCY_UNAVAILABLE"])


if __name__ == "__main__":
    unittest.main()
