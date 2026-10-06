from __future__ import annotations

import unittest

from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.telegram.renderer import (
    action_from_callback_data,
    callback_data_for,
    decode_callback_data,
    render_button,
)


class V3UICallbackPayloadTests(unittest.TestCase):
    def test_payload_round_trip_preserves_action_and_values(self):
        data = callback_data_for(
            UIAction.SELECT_PROFILE,
            (("profile", "Ca/Ca"), ("intent", "recovery")),
        )
        action, payload = decode_callback_data(data)
        self.assertEqual(UIAction.SELECT_PROFILE, action)
        self.assertEqual({"profile": "Ca/Ca", "intent": "recovery"}, payload)
        self.assertEqual(UIAction.SELECT_PROFILE, action_from_callback_data(data))

    def test_existing_payload_free_callbacks_are_byte_for_byte_unchanged(self):
        self.assertEqual(
            "ui:nav.journal",
            callback_data_for(UIAction.OPEN_JOURNAL),
        )

    def test_button_renderer_uses_spec_payload(self):
        button = render_button(
            ButtonSpec(
                button_id="profile.agm",
                label="AGM",
                action=UIAction.SELECT_PROFILE,
                payload=(("profile", "AGM"),),
            )
        )
        self.assertEqual(
            "ui:charge.select_profile?profile=AGM",
            button.callback_data,
        )

    def test_button_spec_rejects_duplicate_or_blank_payload(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ButtonSpec(
                button_id="bad",
                label="bad",
                action=UIAction.SELECT_PROFILE,
                payload=(("profile", "AGM"), ("profile", "EFB")),
            )
        with self.assertRaisesRegex(ValueError, "key"):
            ButtonSpec(
                button_id="bad-key",
                label="bad",
                action=UIAction.SELECT_PROFILE,
                payload=(("", "AGM"),),
            )
        with self.assertRaisesRegex(ValueError, "value"):
            ButtonSpec(
                button_id="bad-value",
                label="bad",
                action=UIAction.SELECT_PROFILE,
                payload=(("profile", ""),),
            )

    def test_decoder_rejects_duplicate_payload_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            decode_callback_data(
                "ui:charge.select_profile?profile=AGM&profile=EFB"
            )

    def test_callback_limit_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "64-byte"):
            callback_data_for(
                UIAction.SELECT_PROFILE,
                (("profile", "X" * 80),),
            )


if __name__ == "__main__":
    unittest.main()
