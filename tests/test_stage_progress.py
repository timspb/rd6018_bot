import unittest

from runtime.ui.components.stage_progress import render_stage_progress_line


def context(stage="MAIN", *, snapshot=None, **overrides):
    value = {
        "is_active": True,
        "snapshot": snapshot or {},
        "current_v": 16.31,
        "current_i": 1.37,
        "temp_ext": 23.0,
        "stage": stage,
        "stage_mix": "MIX",
        "stage_cooling": "COOLING",
        "stage_desulfation": "DESULFATION",
        "is_cv": False,
        "is_cc": False,
        "i_min_recorded": None,
        "v_max_recorded": None,
        "finish_timer_active": False,
        "mix_current_delta_threshold": 0.03,
        "delta_v_exit": 0.03,
        "exit_cv_reached": False,
        "exit_cc_reached": False,
    }
    value.update(overrides)
    return value


class StageProgressRendererTests(unittest.TestCase):
    def test_main_low_current_hold(self):
        result = render_stage_progress_line(context(snapshot={
            "timers": {"remaining_time": "00:30"},
            "hold": {"kind": "low-current hold", "threshold_a": 0.2, "required_sec": 5400},
        }))
        self.assertEqual(result, "🎯 I≤0.20A | ⚪ I 1.37A | ⏳ 1ч 30м hold")

    def test_desulf_timer_escapes_snapshot_text(self):
        result = render_stage_progress_line(context("DESULFATION", snapshot={
            "timers": {"stage_time": "<1ч>", "remaining_time": "01:00"},
            "hold": {"kind": "desulf timer", "elapsed_text": "<40м>", "remaining_text": "<20м>"},
        }))
        self.assertEqual(result, "🎯 2ч | ⚪ &lt;40м&gt; | ⏳ &lt;20м&gt; до SAFE_WAIT")

    def test_mix_delta_timer(self):
        result = render_stage_progress_line(context("MIX", snapshot={
            "hold": {"kind": "mix delta timer", "elapsed_text": "01:20", "remaining_text": "00:40"},
        }))
        self.assertEqual(result, "🎯 Δ подтверждена | ✅ таймер 01:20 | ⏳ 00:40 до SAFE_WAIT")

    def test_safe_wait_hold(self):
        result = render_stage_progress_line(context(snapshot={
            "hold": {"kind": "safe wait", "threshold_v": 13.5, "remaining_text": "00:10"},
        }))
        self.assertEqual(result, "🎯 V≤13.50V | ⚪ V 16.31V | ⏳ 00:10 до выхода")

    def test_mix_cv_and_cc_finish_evidence(self):
        snap = {"hold": {"kind": "mix evidence"}, "timers": {"remaining_time": "01:00"}}
        cv = render_stage_progress_line(context(
            "MIX", snapshot=snap, is_cv=True, i_min_recorded=1.0,
            finish_timer_active=True, exit_cv_reached=True,
        ))
        cc = render_stage_progress_line(context(
            "MIX", snapshot=snap, is_cc=True, v_max_recorded=16.5,
            finish_timer_active=True, exit_cc_reached=True,
        ))
        self.assertEqual(cv, "🎯 ΔI≥0.03A | ✅ ΔI 0.370A | ⏳ 1ч 00м до SAFE_WAIT")
        self.assertEqual(cc, "🎯 ΔV≥0.03V | ✅ ΔV 0.190V | ⏳ 1ч 00м до SAFE_WAIT")

    def test_cooling(self):
        result = render_stage_progress_line(context("COOLING", temp_ext=34.0))
        self.assertEqual(result, "🎯 T≤35°C | ✅ АКБ 34.0°C | ⏳ возврат после остывания")

    def test_absent_snapshot_uses_empty_fallback(self):
        self.assertEqual(render_stage_progress_line(context("MIX")), "")

    def test_inactive_is_empty(self):
        self.assertEqual(render_stage_progress_line(context(is_active=False)), "")


if __name__ == "__main__":
    unittest.main()
