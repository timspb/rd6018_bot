"""Render-only navigation and compatibility state projection."""
import unittest
from types import SimpleNamespace as NS
from runtime.ui.components.hmi_compat_dashboard_state import compat_dashboard_state
from runtime.ui.components.hmi_navigation_keyboards import _graph_keyboard, _more_keyboard, _back_keyboard
from runtime.ui.components.hmi_state import HmiProcessState, HmiAuthority

def app(hands_off=False, active=False, manual=False, observer=None):
    return NS(
        rd_control_mode_manager=NS(hands_off=hands_off),
        charge_controller=NS(is_active=active),
        manual_session_manager=NS(is_active=manual),
        rd_live_mix_observer=observer,
    )

class NavigationProjectionTests(unittest.TestCase):
    def test_keyboard_only_state_never_invents_control_authority(self):
        self.assertIs(compat_dashboard_state(app(), True).process_state,HmiProcessState.CONTAINMENT)
        self.assertIs(compat_dashboard_state(app(), False).process_state,HmiProcessState.IDLE)
        self.assertIs(compat_dashboard_state(app(hands_off=True), True).authority,HmiAuthority.EXTERNAL)
        self.assertIs(compat_dashboard_state(app(active=True),True).authority,HmiAuthority.AUTO)
        self.assertIs(compat_dashboard_state(app(manual=True),True).authority,HmiAuthority.MANUAL)

    def test_graph_navigation_preserves_callbacks(self):
        a=NS(_chart_range_for_user=lambda _: "session",
             CHART_RANGE_30M="30m", CHART_RANGE_2H="2h", CHART_RANGE_SESSION="session")
        row=_graph_keyboard(a,1).inline_keyboard[0]
        self.assertEqual([b.callback_data for b in row],
                         ["operator_graph_30m","operator_graph_2h","operator_graph_session"])
        self.assertEqual(_back_keyboard().inline_keyboard[0][0].callback_data,"operator_done")

    def test_extra_menu_read_only_states(self):
        state=compat_dashboard_state(app(),False)
        callbacks=[b.callback_data for row in _more_keyboard(state).inline_keyboard for b in row]
        self.assertIn("v2_manual_choose",callbacks)
        self.assertEqual(callbacks[-1],"operator_done")
