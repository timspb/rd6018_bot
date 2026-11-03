import tempfile
import types
import unittest

from aiogram import Router
from aiogram.types import InlineKeyboardMarkup
import operator_hmi as hmi
from operator_dashboard import _active_graph_panel_markup
from operator_mix_eligibility import install_mix_action_eligibility
from rd_managed_adoption import install_managed_live_adoption
from test_rd_managed_adoption import FakeHass, FakeGuard, FakeManager, FakeManual


class RealInstallerGraphButtonsTests(unittest.TestCase):
    def test_live_pb_adoption_composes_with_graph_and_mix_filter(self):
        app = types.SimpleNamespace(
            hass=FakeHass(),
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=FakeManual(),
            rd_live_mix_observer=None,
            router=Router(),
            InlineKeyboardMarkup=InlineKeyboardMarkup,
            CHART_RANGE_30M="30m",
            CHART_RANGE_2H="2h",
            CHART_RANGE_SESSION="session",
        )
        app._chart_range_for_user = lambda _: "2h"
        guard = FakeGuard(app)
        manager = FakeManager(app, guard)
        app.rd_control_mode_manager = manager
        app.hass.live["set_voltage"] = 14.65
        base = hmi.build_operator_keyboard
        old_flag = getattr(hmi, "_rd_managed_adoption_keyboard_wrapped", False)
        try:
            install_managed_live_adoption(app, manager, install_ui=True)
            install_mix_action_eligibility(app)
            state = hmi.OperatorHmiState(
                hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL, "",
                True, "-", "", 14.66, 0.05, 26.0, None, 14.65, 1.08,
                None, "", "",
            )
            markup = _active_graph_panel_markup(app, state, 1)
            callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
            self.assertIn("rd_managed_adopt", callbacks)
            self.assertNotIn("rd_live_mix", callbacks)
            self.assertIn("operator_graph_2h", callbacks)
        finally:
            hmi.build_operator_keyboard = base
            hmi._rd_managed_adoption_keyboard_wrapped = old_flag
