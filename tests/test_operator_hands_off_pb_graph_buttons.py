import types
import unittest
from unittest.mock import patch

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import operator_hmi as hmi
from operator_dashboard import _active_graph_panel_markup


class FakeApp:
    CHART_RANGE_30M = "30m"
    CHART_RANGE_2H = "2h"
    CHART_RANGE_SESSION = "session"

    def __init__(self):
        self.rd_control_mode_manager = types.SimpleNamespace(hands_off=True)
        self.charge_controller = types.SimpleNamespace(is_active=False)
        self.manual_session_manager = types.SimpleNamespace(is_active=False)
        self.rd_live_mix_observer = None
        self.InlineKeyboardMarkup = InlineKeyboardMarkup

    def _chart_range_for_user(self, user_id):
        return "2h"


class HandsOffPbGraphButtonsTests(unittest.TestCase):
    def test_graph_keeps_original_pb_adoption_composition(self):
        app = FakeApp()
        state = types.SimpleNamespace(
            process_state=hmi.HmiProcessState.HANDS_OFF,
            output_on=True,
            target_voltage_v=14.65,
        )
        calls = []

        def composed_keyboard(app_arg, state_arg, **kwargs):
            calls.append(kwargs)
            if kwargs:
                return InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Подхватить Mix", callback_data="rd_live_mix")
                ]])
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Забрать под Pb-контроль",
                                      callback_data="rd_managed_adopt")],
                [InlineKeyboardButton(text="Output OFF", callback_data="rd_hands_off_output_off")],
                [InlineKeyboardButton(text="Обновить", callback_data="operator_refresh")],
            ])

        with patch.object(hmi, "build_operator_keyboard", side_effect=composed_keyboard):
            result = _active_graph_panel_markup(app, state, 1, actions=types.SimpleNamespace(available_actions=()))

        callbacks = [button.callback_data for row in result.inline_keyboard for button in row]
        self.assertEqual(calls, [{}], "V3 actions bypass canonical Pb ownership wrappers")
        self.assertIn("rd_managed_adopt", callbacks)
        self.assertNotIn("rd_live_mix", callbacks)
        self.assertIn("operator_graph_2h", callbacks)
        self.assertIn("rd_hands_off_output_off", callbacks)
