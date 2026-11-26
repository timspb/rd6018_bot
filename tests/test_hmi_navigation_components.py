"""Render-only navigation and compatibility state projection."""
import unittest
from types import SimpleNamespace as NS
from runtime.ui.components.hmi_compat_dashboard_state import compat_dashboard_state
from runtime.ui.components.hmi_navigation_keyboards import (
    _back_keyboard,
    _graph_keyboard,
    _more_keyboard,
    chart_label,
    chart_query_params,
    chart_range_for_user,
)
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

    def test_chart_range_projection_preserves_manual_override_and_elapsed_defaults(self):
        a=NS(
            user_chart_range={7:"session"},
            CHART_RANGE_VALUES={"30m","2h","session"},
            CHART_RANGE_DEFAULT="2h", CHART_RANGE_30M="30m",
            CHART_RANGE_2H="2h", CHART_RANGE_SESSION="session",
            charge_controller=NS(is_active=True,total_start_time=1000.0),
        )
        self.assertEqual(chart_range_for_user(a,7,now_s=9000.0),"session")
        a.user_chart_range={}
        self.assertEqual(chart_range_for_user(a,7,now_s=1200.0),"30m")
        self.assertEqual(chart_range_for_user(a,7,now_s=8200.0),"2h")
        self.assertEqual(chart_range_for_user(a,7,now_s=31000.0),"session")

    def test_chart_query_params_and_labels_preserve_legacy_windows(self):
        a=NS(
            user_chart_range={}, CHART_RANGE_VALUES={"30m","2h","session"},
            CHART_RANGE_DEFAULT="2h", CHART_RANGE_30M="30m",
            CHART_RANGE_2H="2h", CHART_RANGE_SESSION="session",
            charge_controller=NS(is_active=True,total_start_time=1000.0),
        )
        mode,start,limit=chart_query_params(a,1,now_s=1200.0)
        self.assertEqual((mode,start,limit),("30m",-600.0,120))
        a.user_chart_range={1:"session"}
        self.assertEqual(chart_query_params(a,1,now_s=5000.0),("session",1000.0,500))
        self.assertEqual(chart_label(a,"30m"),"30м")
        self.assertEqual(chart_label(a,"session"),"Сессия")
