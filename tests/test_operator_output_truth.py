import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import operator_hmi as hmi
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
