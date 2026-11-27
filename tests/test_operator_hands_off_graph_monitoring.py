import time
import types
import unittest
from unittest.mock import patch

from aiogram.types import InlineKeyboardMarkup

from operator_dashboard import (
    _charge_session_active,
    _graph_display_allowed,
    _graph_query_params,
    _graph_toolbar,
)


class FakeGraphMonitoringApp:
    CHART_RANGE_30M = "30m"
    CHART_RANGE_2H = "2h"
    CHART_RANGE_SESSION = "session"

    def __init__(self, hands_off):
        self.rd_control_mode_manager = types.SimpleNamespace(hands_off=hands_off)
        self.charge_controller = types.SimpleNamespace(is_active=False)
        self.manual_session_manager = types.SimpleNamespace(is_active=False)
        self.rd_live_mix_observer = None
        self.selected_range = self.CHART_RANGE_SESSION

    def _chart_range_for_user(self, user_id):
        return self.selected_range

    def _chart_query_params(self, user_id):
        return self.CHART_RANGE_2H, time.time()-7200, 300


class HandsOffGraphMonitoringTests(unittest.TestCase):
    def test_hands_off_monitoring_does_not_claim_managed_session(self):
        app = FakeGraphMonitoringApp(hands_off=True)
        self.assertFalse(_charge_session_active(app))
        self.assertTrue(_graph_display_allowed(app))
        mode, since, limit = _graph_query_params(app, 42)
        self.assertEqual(mode, app.CHART_RANGE_SESSION)
        self.assertEqual(limit, 500)
        self.assertLess(abs((time.time()-since)-86400), 3)

    def test_idle_without_hands_off_keeps_existing_graph_boundary(self):
        app = FakeGraphMonitoringApp(hands_off=False)
        self.assertFalse(_graph_display_allowed(app))
        self.assertEqual(_graph_query_params(app, 42)[0], app.CHART_RANGE_2H)

    def test_graph_policy_covers_owners_and_preserves_ordinary_ranges(self):
        app = FakeGraphMonitoringApp(hands_off=False)
        for owner in ("charge_controller", "manual_session_manager"):
            setattr(app, owner, types.SimpleNamespace(is_active=True))
            self.assertTrue(_charge_session_active(app))
            self.assertTrue(_graph_display_allowed(app))
            query = _graph_query_params(app, 42)
            self.assertEqual(query[0], app.CHART_RANGE_2H)
            self.assertEqual(query[2], 300)
            self.assertAlmostEqual(query[1], time.time()-7200, delta=1)
            setattr(app, owner, types.SimpleNamespace(is_active=False))

        for state in ("active", "off_pending"):
            app.rd_live_mix_observer = types.SimpleNamespace(state=state)
            self.assertTrue(_charge_session_active(app))
            self.assertTrue(_graph_display_allowed(app))
        app.rd_live_mix_observer = None

        app.rd_control_mode_manager.hands_off = True
        self.assertTrue(_graph_display_allowed(app))
        app.selected_range = app.CHART_RANGE_30M
        ordinary = _graph_query_params(app, 42)
        self.assertEqual(ordinary[0], app.CHART_RANGE_2H)
        self.assertEqual(ordinary[2], 300)
        self.assertAlmostEqual(ordinary[1], time.time()-7200, delta=1)

    def test_hands_off_toolbar_labels_history_not_managed_session(self):
        app = FakeGraphMonitoringApp(hands_off=True)
        with patch("operator_dashboard.hmi._graph_keyboard") as graph_keyboard:
            from aiogram.types import InlineKeyboardButton
            graph_keyboard.return_value = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="30м",callback_data="operator_graph_30m"),
                InlineKeyboardButton(text="2ч",callback_data="operator_graph_2h"),
                InlineKeyboardButton(text="● Сессия",callback_data="operator_graph_session"),
            ]])
            row = _graph_toolbar(app, 1)
        self.assertEqual(row[2].text, "● 24ч")
        self.assertEqual(row[2].callback_data, "operator_graph_session")
