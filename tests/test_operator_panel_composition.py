"""Text and graph workspaces reuse installed RD ownership keyboard composition."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import operator_dashboard
import operator_hmi


def app(*, charging=False):
    return SimpleNamespace(
        InlineKeyboardMarkup=InlineKeyboardMarkup,
        charge_controller=SimpleNamespace(is_active=charging),
        manual_session_manager=SimpleNamespace(is_active=False),
        rd_live_mix_observer=None,
    )


class OperatorPanelCompositionTests(unittest.TestCase):
    def test_normal_panel_hides_release_only_during_charge(self):
        original = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="release", callback_data="rd_hands_off_release_confirm")],
            [InlineKeyboardButton(text="status", callback_data="operator_refresh")],
        ])
        with patch.object(operator_hmi, "build_operator_keyboard", return_value=original) as build:
            idle = operator_dashboard._main_graph_markup(app(), object(), 1)
            charging = operator_dashboard._main_graph_markup(app(charging=True), object(), 1)
        self.assertEqual(build.call_count, 2)
        self.assertIn("rd_hands_off_release_confirm", self._callbacks(idle))
        self.assertNotIn("rd_hands_off_release_confirm", self._callbacks(charging))
        self.assertIn("operator_refresh", self._callbacks(charging))

    @staticmethod
    def _callbacks(markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]
