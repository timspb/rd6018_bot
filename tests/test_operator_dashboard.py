import asyncio
import io
import types
import unittest
from datetime import datetime, timedelta, timezone

import operator_hmi as hmi
from operator_dashboard import (
    build_truthful_hmi_state,
    install_operator_graph_dashboard,
    render_truthful_panel,
)
from operator_hmi import HmiProcessState, build_operator_keyboard


class FakeApp:
    def __init__(self):
        self.rd_control_mode_manager = types.SimpleNamespace(hands_off=False)
        self.rd_live_mix_observer = None
        self.charge_controller = types.SimpleNamespace(
            is_active=False,
            current_stage="Idle",
            battery_type="",
            ah_capacity=0,
        )
        self.manual_session_manager = types.SimpleNamespace(is_active=False)
        self.CHART_RANGE_30M = "30m"
        self.CHART_RANGE_2H = "2h"
        self.CHART_RANGE_SESSION = "session"


def _live(**overrides):
    data = {
        "switch": "off",
        "battery_voltage": 13.10,
        "current": 0.0,
        "power": 0.0,
        "temp_ext": 25.0,
        "temp_int": 35.0,
        "set_voltage": 14.8,
        "set_current": 5.0,
        "is_cv": "off",
        "is_cc": "off",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
    }
    data.update(overrides)
    return data


def _callbacks(app, state):
    return {
        button.callback_data
        for row in build_operator_keyboard(app, state).inline_keyboard
        for button in row
        if button.callback_data
    }


class OperatorDashboardTruthTests(unittest.TestCase):
    def test_unknown_output_is_containment_not_idle_or_off(self):
        app = FakeApp()
        state = build_truthful_hmi_state(app, _live(switch="unavailable"))
        text = render_truthful_panel(state)
        callbacks = _callbacks(app, state)

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "output_unknown")
        self.assertIn("OUTPUT НЕ ПОДТВЕРЖДЁН", text)
        self.assertIn("Output <b>UNKNOWN</b>", text)
        self.assertNotIn("Output <b>OFF</b>", text)
        self.assertNotIn("charge_modes", callbacks)
        self.assertNotIn("v2_manual_choose", callbacks)

    def test_stale_output_is_containment_even_when_last_value_says_on(self):
        app = FakeApp()
        old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        state = build_truthful_hmi_state(
            app,
            _live(
                switch="on",
                _meta={
                    "switch": {
                        "status": "ok",
                        "last_reported": old,
                        "last_updated": old,
                    }
                },
            ),
        )
        text = render_truthful_panel(state)

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "output_unknown")
        self.assertIn("Output <b>UNKNOWN</b>", text)
        self.assertIn("устарела", state.progress)

    def test_missing_protection_status_contains_idle_and_hides_start(self):
        app = FakeApp()
        live = _live()
        live.pop("ocp_triggered")
        state = build_truthful_hmi_state(app, live)
        text = render_truthful_panel(state)
        callbacks = _callbacks(app, state)

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "warning")
        self.assertIn("ЗАЩИТА НЕ ПОДТВЕРЖДЕНА", text)
        self.assertIn("Статус защит RD6018 не подтверждён", text)
        self.assertNotIn("Защита: норма", text)
        self.assertNotIn("charge_modes", callbacks)
        self.assertNotIn("v2_manual_choose", callbacks)

    def test_confirmed_off_and_protections_remain_normal_idle(self):
        app = FakeApp()
        state = build_truthful_hmi_state(app, _live())
        text = render_truthful_panel(state)

        self.assertEqual(state.process_state, HmiProcessState.IDLE)
        self.assertIn("Output <b>OFF</b>", text)
        self.assertIn("Защита: норма", text)
        self.assertIn("charge_modes", _callbacks(app, state))

    def test_unknown_protection_while_output_on_is_alarm(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(switch="on", ovp_triggered="unknown"),
        )

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "alarm")
        self.assertIn("Статус защит RD6018 не подтверждён", state.safety)

    def test_raw_opp_trip_is_visible_and_idle_start_is_withheld(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(protection_code=3),
        )
        text = render_truthful_panel(state)
        callbacks = _callbacks(app, state)

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "alarm")
        self.assertIn("СРАБОТАЛА ЗАЩИТА OPP", text)
        self.assertIn("Защита: OPP", text)
        self.assertNotIn("Защита: норма", text)
        self.assertNotIn("charge_modes", callbacks)
        self.assertNotIn("v2_manual_choose", callbacks)

    def test_raw_opp_trip_is_visible_even_when_legacy_bits_are_off_while_on(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(switch="on", protection_code=3),
        )
        text = render_truthful_panel(state)

        self.assertEqual(state.attention, "alarm")
        self.assertIn("Защита: OPP", text)
        self.assertNotIn("Защита: норма", text)

    def test_unknown_raw_protection_code_is_not_downgraded_by_legacy_bits(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(switch="on", protection_code=99),
        )

        self.assertEqual(state.attention, "alarm")
        self.assertIn("Статус защит RD6018 не подтверждён", state.safety)

    def test_stale_raw_protection_contains_idle_even_when_code_was_normal(self):
        app = FakeApp()
        old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        live = _live(
            protection_code=0,
            _meta={
                "switch": {"status": "ok", "last_reported": now, "last_updated": now},
                "protection_code": {"status": "ok", "last_reported": old, "last_updated": old},
            },
        )
        state = build_truthful_hmi_state(app, live)

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertNotIn("charge_modes", _callbacks(app, state))
        self.assertIn("Статус защит RD6018 не подтверждён", state.safety)

    def test_raw_regulation_code_overrides_legacy_mode_flags(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(switch="on", regulation_code=1, is_cv="on", is_cc="off"),
        )

        self.assertEqual(state.regulator, "CC")


class FakeGraphBot:
    def __init__(self):
        self.media_edits = []

    async def edit_message_media(self, **kwargs):
        self.media_edits.append(kwargs)
        return True


class FakeGraphMessage:
    def __init__(self):
        self.chat = types.SimpleNamespace(id=10)
        self.message_id = 77
        self.answers = []

    async def answer_photo(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return types.SimpleNamespace(message_id=78)

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return types.SimpleNamespace(message_id=78)


class FakeGraphApp(FakeApp):
    def __init__(self):
        super().__init__()
        self.bot = FakeGraphBot()
        self.asyncio = asyncio
        self.ParseMode = types.SimpleNamespace(HTML="HTML")
        self.BufferedInputFile = lambda payload, filename: (payload, filename)
        self.InputMediaPhoto = lambda **kwargs: kwargs
        self.user_dashboard = {}
        self.chat_dashboard = {}
        self.user_chart_range = {1: self.CHART_RANGE_2H}
        self._build_and_send_dashboard = None

    def _chart_range_for_user(self, user_id):
        return self.user_chart_range.get(user_id, self.CHART_RANGE_30M)

    def _chart_query_params(self, user_id):
        return self._chart_range_for_user(user_id), None, 120

    async def get_graph_data_with_temp(self, *, limit, since_timestamp):
        return [1, 2], [13.0, 13.1], [1.0, 0.9], [25.0, 25.1]

    @staticmethod
    def generate_chart(times, voltages, currents, temps):
        return io.BytesIO(b"png")


class OperatorGraphWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_range_change_edits_existing_graph_workspace(self):
        app = FakeGraphApp()
        call = types.SimpleNamespace(message=FakeGraphMessage())
        old_builder = hmi.build_operator_hmi_state
        old_panel = hmi.render_operator_panel
        old_details = hmi.render_operator_details
        old_graph = hmi._render_graph_workspace
        try:
            install_operator_graph_dashboard(app)
            await hmi._render_graph_workspace(app, call, 1)
        finally:
            hmi.build_operator_hmi_state = old_builder
            hmi.render_operator_panel = old_panel
            hmi.render_operator_details = old_details
            hmi._render_graph_workspace = old_graph

        self.assertEqual(len(app.bot.media_edits), 1)
        self.assertEqual(app.bot.media_edits[0]["message_id"], 77)
        self.assertEqual(call.message.answers, [])


if __name__ == "__main__":
    unittest.main()
