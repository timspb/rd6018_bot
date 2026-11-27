import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import types
from pathlib import Path
import operator_hmi as hmi
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA
from operator_output_truth import install_operator_output_truth
from operator_output_truth import (
    _render_unknown_output,
    filter_keyboard_for_output_truth,
    normalize_operator_state,
    output_known,
    output_truth,
)


def _live(switch, *, age_s=0.0):
    reported = (datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat()
    return {
        "switch": switch,
        "_meta": {
            "switch": {
                "status": "ok",
                "last_reported": reported,
                "last_updated": reported,
            }
        },
    }


def _state(process, authority, *, output_on=False):
    return hmi.OperatorHmiState(
        process_state=process,
        authority=authority,
        title="RD6018",
        output_on=output_on,
        regulator="CV",
        battery_label="",
        battery_voltage_v=None,
        current_a=None,
        power_w=None,
        battery_temp_c=None,
        psu_temp_c=None,
        target_voltage_v=None,
        current_limit_a=None,
        progress="",
        safety="Защита: норма",
    )


def _app(*, managed=False):
    return SimpleNamespace(
        charge_controller=SimpleNamespace(is_active=managed),
        manual_session_manager=SimpleNamespace(is_active=False),
    )


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


class OperatorOutputTruthTests(unittest.TestCase):
    @staticmethod
    def _mix_coordinator(*, active=True, off_pending=False, battery="A"):
        return SimpleNamespace(
            active=active,
            off_pending=off_pending,
            battery_id=battery,
            chemistry=None,
            capacity_ah=72,
            total_active_elapsed_s=3600,
            hard_limit_s=20 * 3600,
            prior_elapsed_s=1800,
            prior_age_source="declared",
            current_authority=SimpleNamespace(set_voltage_v=16.5, set_current_a=1.0),
            finish_hold_started_at_s=None,
            last_status="watching",
        )

    def test_d062_projection_keyboard_and_details_use_each_apps_coordinator(self):
        app_a = _app()
        app_b = _app()
        app_a.rd_managed_mix_adoption = self._mix_coordinator(battery="Battery <A>")
        app_b.rd_managed_mix_adoption = self._mix_coordinator(
            active=False, off_pending=True, battery="Battery B"
        )

        state_a = hmi.build_operator_hmi_state(app_a, _live("on"))
        state_b = hmi.build_operator_hmi_state(app_b, _live("on"))
        self.assertEqual(state_a.title, "RD6018 · MIX ПОД УПРАВЛЕНИЕМ")
        self.assertEqual(state_b.title, "RD6018 · MIX · OFF PENDING")
        self.assertEqual(state_a.battery_label, "Battery <A> · 72 Ah")
        self.assertEqual(state_b.battery_label, "Battery B · 72 Ah")
        self.assertEqual(
            _callbacks(hmi.build_operator_keyboard(app_a, state_a)),
            {"operator_managed_mix_stop", "operator_details", "operator_graph", "v2_batteries"},
        )
        details = hmi.render_operator_details(app_a, state_a, _live("on"))
        self.assertIn("Prior age", details)
        self.assertIn("Active budget", details)
        self.assertIn("16.50V/1.00A", details)
        self.assertIn("Battery &lt;A&gt;", details)
        self.assertIn("UNKNOWN", hmi.render_operator_details(app_a, hmi.build_operator_hmi_state(app_a, _live("unknown")), _live("unknown")))
        self.assertIn("Output: OFF", hmi.render_operator_details(
            app_a, hmi.build_operator_hmi_state(app_a, _live("off")), _live("off")
        ))

    def test_d062_idle_entry_requires_hands_off_on_high_voltage_and_autonomous_suppresses_it(self):
        app = _app()
        app.rd_managed_mix_adoption = self._mix_coordinator(active=False)
        app.rd_control_mode_manager = SimpleNamespace(hands_off=True)
        state = _state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL, output_on=True)
        state = hmi.replace(state, target_voltage_v=16.5)
        markup = hmi.build_operator_keyboard(app, state)
        self.assertIn("rd_managed_mix", _callbacks(markup))

        app.rd_autonomous_mode = SimpleNamespace(manager=SimpleNamespace(edge_autonomous=True))
        self.assertNotIn("rd_managed_mix", _callbacks(hmi.build_operator_keyboard(app, state)))

    def test_d062_no_app_more_keyboard_remains_compatible(self):
        state = _state(hmi.HmiProcessState.ADOPTED_MIX, hmi.HmiAuthority.ADOPTED_MIX)
        self.assertIn("rd_live_mix_status", _callbacks(hmi._more_keyboard(state)))

    def test_install_is_app_scoped_and_two_apps_do_not_share_output_eligibility(self):
        builders = (
            hmi.build_operator_hmi_state,
            hmi.build_operator_keyboard,
            hmi._more_keyboard,
            hmi.render_operator_details,
            hmi.render_operator_service_details,
        )
        app_a = _app()
        app_b = _app()

        install_operator_output_truth(app_a)
        install_operator_output_truth(app_b)

        self.assertEqual(
            builders,
            (
                hmi.build_operator_hmi_state,
                hmi.build_operator_keyboard,
                hmi._more_keyboard,
                hmi.render_operator_details,
                hmi.render_operator_service_details,
            ),
            "installing per-app output truth must not replace process-global HMI builders",
        )

        unknown = hmi.build_operator_hmi_state(app_a, _live("unknown"))
        confirmed_off = hmi.build_operator_hmi_state(app_b, _live("off"))
        self.assertFalse(output_known(unknown))
        self.assertTrue(output_known(confirmed_off))
        self.assertNotIn(
            CHARGE_CALLBACK_DATA,
            _callbacks(hmi.build_operator_keyboard(app_a, unknown)),
        )
        self.assertIn(
            CHARGE_CALLBACK_DATA,
            _callbacks(hmi.build_operator_keyboard(app_b, confirmed_off)),
        )
        self.assertTrue(app_a._operator_output_truth_installed)
        self.assertTrue(app_b._operator_output_truth_installed)

    def test_source_no_longer_assigns_global_hmi_builders_from_output_installer(self):
        source = Path("operator_output_truth.py").read_text(encoding="utf-8")
        for assignment in (
            "hmi.build_operator_hmi_state =",
            "hmi.build_operator_keyboard =",
            "hmi._more_keyboard =",
            "hmi.render_operator_details =",
            "hmi.render_operator_service_details =",
        ):
            self.assertNotIn(assignment, source)
        hmi_source = Path("operator_hmi.py").read_text(encoding="utf-8")
        self.assertIn("return normalize_operator_state(app, state, live, hmi)", hmi_source)
        self.assertIn("return filter_keyboard_for_output_truth(app, state, markup, hmi)", hmi_source)
        self.assertIn("return _render_unknown_output(_render_operator_details(app, state, live), state)", hmi_source)
        self.assertIn("return _render_unknown_output(_render_operator_service_details(app, state, live), state)", hmi_source)
        self.assertIn("_more_keyboard(state, app)", hmi_source)
        self.assertIn("return normalize_operator_state(app, state, live, hmi)", hmi_source)

    def test_fresh_unknown_is_not_off(self):
        physical, known = output_truth(_live("unknown"))
        self.assertIsNone(physical)
        self.assertFalse(known)

    def test_stale_off_is_not_proof_of_off(self):
        physical, known = output_truth(_live("off", age_s=300.0))
        self.assertIsNone(physical)
        self.assertFalse(known)

    def test_fresh_off_remains_proven_off(self):
        physical, known = output_truth(_live("off"))
        self.assertIs(physical, False)
        self.assertTrue(known)

    def test_pb_managed_unknown_output_is_containment_not_idle(self):
        state = _state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE)
        normalized = normalize_operator_state(_app(), state, _live("unknown"), hmi)

        self.assertEqual(normalized.process_state, hmi.HmiProcessState.CONTAINMENT)
        self.assertEqual(normalized.authority, hmi.HmiAuthority.CONTAINMENT)
        self.assertIn("НЕ ПОДТВЕРЖДЁН", normalized.title)
        self.assertFalse(output_known(normalized))
        self.assertIn("UNKNOWN", normalized.safety)

    def test_final_filter_removes_managed_stop_for_unknown_and_autonomous(self):
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Stop", callback_data="operator_managed_stop"),
            InlineKeyboardButton(text="Details", callback_data="operator_details"),
        ]])
        unknown = normalize_operator_state(
            _app(), _state(hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO), _live("unknown"), hmi
        )
        self.assertNotIn(
            "operator_managed_stop",
            _callbacks(filter_keyboard_for_output_truth(_app(), unknown, markup, hmi)),
        )

        app = _app()
        app.rd_autonomous_mode = SimpleNamespace(
            manager=SimpleNamespace(edge_autonomous=True),
            _entry_transition_pending=False,
            _entry_uncertain=False,
        )
        known = _state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL, output_on=True)
        self.assertNotIn(
            "operator_managed_stop",
            _callbacks(filter_keyboard_for_output_truth(app, known, markup, hmi)),
        )

    def test_hands_off_unknown_stays_hands_off_but_never_claims_free_off(self):
        state = _state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL)
        normalized = normalize_operator_state(_app(), state, _live("unavailable"), hmi)

        self.assertEqual(normalized.process_state, hmi.HmiProcessState.HANDS_OFF)
        self.assertFalse(output_known(normalized))
        self.assertIn("не подтверждено", normalized.progress)
        self.assertNotIn("свободен", normalized.progress)

    def test_hands_off_unknown_hides_pb_return_and_offers_verified_off_resolution(self):
        state = normalize_operator_state(
            _app(),
            _state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL),
            _live("unknown"),
            hmi,
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Return", callback_data="rd_hands_off_disable")],
                [InlineKeyboardButton(text="Mix", callback_data="rd_live_mix")],
                [InlineKeyboardButton(text="Refresh", callback_data="operator_refresh")],
            ]
        )

        filtered = filter_keyboard_for_output_truth(_app(), state, markup, hmi)
        callbacks = _callbacks(filtered)
        self.assertNotIn("rd_hands_off_disable", callbacks)
        self.assertNotIn("rd_live_mix", callbacks)
        self.assertIn("rd_hands_off_output_off", callbacks)
        self.assertIn("operator_refresh", callbacks)

    def test_pb_unknown_hides_live_adoption_and_hands_off_transfer(self):
        state = normalize_operator_state(
            _app(),
            _state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE),
            _live("unknown"),
            hmi,
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Adopt", callback_data="rd_ownership_adopt")],
                [InlineKeyboardButton(text="Hands off", callback_data="rd_ownership_hands_off")],
                [InlineKeyboardButton(text="Modes", callback_data="charge_modes")],
                [InlineKeyboardButton(text="Refresh", callback_data="operator_refresh")],
            ]
        )

        filtered = filter_keyboard_for_output_truth(_app(), state, markup, hmi)
        callbacks = _callbacks(filtered)
        self.assertNotIn("rd_ownership_adopt", callbacks)
        self.assertNotIn("rd_ownership_hands_off", callbacks)
        self.assertNotIn("charge_modes", callbacks)
        self.assertIn("rd_ownership_output_off", callbacks)
        self.assertIn("operator_refresh", callbacks)

    def test_output_truth_final_filter_removes_invalid_autonomous_controls(self):
        state = _state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL, output_on=True)
        object.__setattr__(state, "_output_state_known", True)
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Exit", callback_data="rd_autonomous_exit"),
            InlineKeyboardButton(text="Enter", callback_data="rd_autonomous_confirm"),
        ]])
        filtered = filter_keyboard_for_output_truth(_app(), state, markup, hmi)
        self.assertEqual(_callbacks(filtered), set())

    def test_autonomous_unknown_output_does_not_gain_bot_off_action(self):
        state = normalize_operator_state(
            _app(),
            _state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL),
            _live("unknown"),
            hmi,
        )
        autonomous = types.SimpleNamespace(
            manager=types.SimpleNamespace(edge_autonomous=True),
            _entry_transition_pending=False,
            _entry_uncertain=False,
        )
        app = types.SimpleNamespace(rd_autonomous_mode=autonomous)
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Exit", callback_data="rd_autonomous_exit"),
            InlineKeyboardButton(text="OFF", callback_data="rd_hands_off_output_off"),
        ]])
        filtered = filter_keyboard_for_output_truth(app, state, markup, hmi)
        self.assertEqual(_callbacks(filtered), set())

    def test_unknown_details_never_render_output_off(self):
        state = normalize_operator_state(
            _app(),
            _state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE),
            _live("unknown"),
            hmi,
        )
        text = _render_unknown_output("Output: <b>OFF</b>\nOutput: <code>OFF</code>", state)
        self.assertNotIn("Output: <b>OFF</b>", text)
        self.assertNotIn("Output: <code>OFF</code>", text)
        self.assertIn("UNKNOWN", text)


if __name__ == "__main__":
    unittest.main()
