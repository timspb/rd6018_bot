import asyncio
import io
import types
import unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone

import operator_hmi as hmi
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from operator_dashboard import (
    _active_graph_panel_markup,
    _panel_actions,
    _toolbar_actions,
    build_truthful_hmi_state,
    install_operator_graph_dashboard,
    render_truthful_panel,
)
from operator_hmi import HmiProcessState, build_operator_keyboard
from application.operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from runtime.ui.components.hmi_action_keyboard import (
    _panel_actions as component_panel_actions,
    _toolbar_actions as component_toolbar_actions,
)
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA
from runtime.ui.telegram.panel_lifecycle import TerminalPanelManager


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


class OperatorActionViewFilterTests(unittest.TestCase):
    def setUp(self):
        self.actions = OperatorActionsView(tuple(
            OperatorActionSpec(action)
            for action in (
                OperatorAction.SHOW_LOG,
                OperatorAction.SHOW_DIAGNOSTICS,
                OperatorAction.SHOW_GRAPH,
                OperatorAction.START_CHARGE,
            )
        ))

    def test_dashboard_names_remain_direct_component_imports(self):
        self.assertIs(_panel_actions, component_panel_actions)
        self.assertIs(_toolbar_actions, component_toolbar_actions)

    def test_dashboard_install_is_app_bound_and_leaves_hmi_globals_untouched(self):
        app_a, app_b = FakeGraphApp(), FakeGraphApp()
        app_a._graph_probe = "a"
        app_b._graph_probe = "b"
        builder = hmi.build_operator_hmi_state
        panel = hmi.render_operator_panel
        details = hmi.render_operator_details
        graph = hmi._render_graph_workspace
        install_operator_graph_dashboard(app_a)
        renderer_a = app_a._render_graph_workspace
        install_operator_graph_dashboard(app_b)
        self.assertIs(hmi.build_operator_hmi_state, builder)
        self.assertIs(hmi.render_operator_panel, panel)
        self.assertIs(hmi.render_operator_details, details)
        self.assertIs(hmi._render_graph_workspace, graph)
        self.assertIsNot(renderer_a, app_b._render_graph_workspace)

    def test_graph_keyboard_exports_are_direct_telegram_adapter_functions(self):
        import operator_dashboard as dashboard
        from runtime.ui.telegram import operator_graph_keyboard as layout
        for name in (
            "_hide_active_release_button", "_graph_toolbar",
            "_composed_operator_rows", "_main_graph_markup",
            "_active_graph_panel_markup",
        ):
            self.assertIs(getattr(dashboard, name), getattr(layout, name))

    def test_release_filter_does_not_mutate_input(self):
        import operator_dashboard as dashboard
        source = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Release", callback_data="rd_hands_off_release_confirm"),
            InlineKeyboardButton(text="Refresh", callback_data="operator_refresh"),
        ]])
        result = dashboard._hide_active_release_button(source)
        self.assertEqual([b.callback_data for row in result.inline_keyboard for b in row], ["operator_refresh"])
        self.assertEqual(len(source.inline_keyboard[0]), 2)

    def test_none_is_preserved_by_both_filters(self):
        self.assertIsNone(_panel_actions(None, dark=True))
        self.assertIsNone(_panel_actions(None, dark=False))
        self.assertIsNone(_toolbar_actions(None))

    def test_non_dark_panel_returns_same_view(self):
        self.assertIs(_panel_actions(self.actions, dark=False), self.actions)

    def test_dark_panel_filters_only_diagnostics_and_preserves_order(self):
        result = _panel_actions(self.actions, dark=True)

        self.assertEqual(
            tuple(item.action for item in result.available_actions),
            (OperatorAction.SHOW_LOG, OperatorAction.SHOW_GRAPH, OperatorAction.START_CHARGE),
        )
        self.assertEqual(
            tuple(item.action for item in self.actions.available_actions),
            (OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS,
             OperatorAction.SHOW_GRAPH, OperatorAction.START_CHARGE),
        )
        self.assertIsNot(result, self.actions)

    def test_toolbar_filters_only_graph_and_preserves_order_and_input(self):
        result = _toolbar_actions(self.actions)

        self.assertEqual(
            tuple(item.action for item in result.available_actions),
            (OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS, OperatorAction.START_CHARGE),
        )
        self.assertEqual(
            tuple(item.action for item in self.actions.available_actions),
            (OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS,
             OperatorAction.SHOW_GRAPH, OperatorAction.START_CHARGE),
        )
        self.assertIsNot(result, self.actions)


class OperatorDashboardTruthTests(unittest.TestCase):
    def test_semantic_owner_and_dashboard_compatibility_exports(self):
        import operator_dashboard as dashboard

        self.assertIs(dashboard._binary, hmi._binary)
        self.assertIs(dashboard._fresh, hmi._fresh)
        self.assertIs(dashboard._raw_available, hmi._raw_available)
        self.assertIs(dashboard._regulation_fresh, hmi._regulation_fresh)
        self.assertIs(dashboard._ownership_conflict, hmi._ownership_conflict)
        self.assertIs(dashboard._contain_idle_for_safety, hmi._contain_idle_for_safety)
        self.assertIsNot(dashboard.build_truthful_hmi_state, hmi.build_truthful_hmi_state)

    def test_dashboard_delegate_honors_captured_base_builder_once(self):
        app = FakeApp()
        live = _live()
        calls = []
        original = hmi._BASE_BUILD_OPERATOR_HMI_STATE

        def base_builder(app_arg, live_arg):
            calls.append((app_arg, live_arg))
            return original(app_arg, live_arg)

        state = build_truthful_hmi_state(app, live, base_builder=base_builder)

        self.assertEqual(calls, [(app, live)])
        self.assertEqual(state.process_state, HmiProcessState.IDLE)

    def test_unknown_output_is_containment_not_idle_or_off(self):
        app = FakeApp()
        state = build_truthful_hmi_state(app, _live(switch="unavailable"))
        text = render_truthful_panel(state)
        callbacks = _callbacks(app, state)

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "output_unknown")
        self.assertIn("OUTPUT НЕ ПОДТВЕРЖДЁН", text)
        self.assertNotIn("Output <b>OFF</b>", text)
        self.assertNotIn(CHARGE_CALLBACK_DATA, callbacks)
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
        self.assertIn("OUTPUT НЕ ПОДТВЕРЖДЁН", text)
        self.assertIn("устарела", state.progress)

    def test_missing_retired_ocp_flag_does_not_create_false_containment(self):
        app = FakeApp()
        live = _live()
        live.pop("ocp_triggered")
        state = build_truthful_hmi_state(app, live)
        text = render_truthful_panel(state)

        self.assertEqual(state.process_state, HmiProcessState.IDLE)
        self.assertIn(CHARGE_CALLBACK_DATA, _callbacks(app, state))
        self.assertNotIn("СРАБОТАЛА ЗАЩИТА", text)

    def test_confirmed_off_and_protections_remain_normal_idle(self):
        app = FakeApp()
        state = build_truthful_hmi_state(app, _live(protection_code=0))
        text = render_truthful_panel(state)

        self.assertEqual(state.process_state, HmiProcessState.IDLE)
        self.assertNotIn("Output <b>", text)
        self.assertIn("Защита: норма", text)
        self.assertIn(CHARGE_CALLBACK_DATA, _callbacks(app, state))

    def test_unknown_protection_while_output_on_is_alarm(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(switch="on", ovp_triggered="unknown"),
        )

        self.assertEqual(state.process_state, HmiProcessState.CONTAINMENT)
        self.assertEqual(state.attention, "alarm")
        self.assertIn("Требуется проверка ownership", state.safety)

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
        self.assertIn("СРАБОТАЛА ЗАЩИТА", text)
        self.assertIn("Защита сработала", text)
        self.assertNotIn("Защита: норма", text)
        self.assertNotIn(CHARGE_CALLBACK_DATA, callbacks)
        self.assertNotIn("v2_manual_choose", callbacks)

    def test_raw_opp_trip_is_visible_even_when_legacy_bits_are_off_while_on(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(switch="on", protection_code=3),
        )
        text = render_truthful_panel(state)

        self.assertEqual(state.attention, "alarm")
        self.assertIn("Защита сработала", text)
        self.assertNotIn("Защита: норма", text)

    def test_unknown_raw_protection_code_is_not_downgraded_by_legacy_bits(self):
        app = FakeApp()
        state = build_truthful_hmi_state(
            app,
            _live(switch="on", protection_code=99),
        )

        self.assertEqual(state.attention, "alarm")
        self.assertIn("Требуется проверка ownership", state.safety)

    def test_stale_neutral_raw_code_does_not_create_idle_alarm(self):
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

        self.assertEqual(state.process_state, HmiProcessState.IDLE)
        self.assertIn(CHARGE_CALLBACK_DATA, _callbacks(app, state))
        self.assertNotIn("СРАБОТАЛА ЗАЩИТА", state.safety)

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
        self.deleted = []
        self.caption_edits = []
        self.photo_sends = []

    async def send_photo(self, chat_id, **kwargs):
        self.photo_sends.append((chat_id, kwargs))
        return types.SimpleNamespace(message_id=90)

    async def edit_message_media(self, **kwargs):
        self.media_edits.append(kwargs)
        return True

    async def edit_message_caption(self, **kwargs):
        self.caption_edits.append(kwargs)
        return True

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))
        return True

    async def send_message(self, *args, **kwargs):
        return types.SimpleNamespace(message_id=88)


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
        self.charge_controller.is_active = True
        self.bot = FakeGraphBot()
        self.asyncio = asyncio
        self.ParseMode = types.SimpleNamespace(HTML="HTML")
        self.BufferedInputFile = lambda payload, filename: (payload, filename)
        self.InputMediaPhoto = lambda **kwargs: kwargs
        self.user_dashboard = {}
        self.chat_dashboard = {}
        self.user_graph_dashboard = {}
        self.chat_graph_dashboard = {}
        self._graph_cache_keys = {}
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
    async def test_initial_graph_dashboard_uses_terminal_publication_owner(self):
        app = FakeGraphApp()
        app.terminal_panel_manager = TerminalPanelManager(app)
        app.operator_interface = types.SimpleNamespace(
            get_operator_snapshot=AsyncMock(return_value=object()),
            get_operator_actions=AsyncMock(return_value=None),
        )
        app.InlineKeyboardMarkup = InlineKeyboardMarkup
        state = hmi.OperatorHmiState(
            hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO, "RD",
            True, "CV", "EFB", 14.76, 0.23, 17.0, 26.0, 35.0, 14.8, 8.0, "", "OK",
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[])
        install_operator_graph_dashboard(app)
        with patch("operator_dashboard.OperatorSnapshotProvider.hmi_state_from_snapshot", return_value=state), \
                patch("operator_dashboard._dark_panel_enabled", return_value=False), \
                patch("operator_dashboard._graph_display_allowed", return_value=True), \
                patch("operator_dashboard._main_graph_markup", return_value=markup):
            message_id = await app._build_and_send_dashboard(10, 1)

        owner = app.terminal_panel_manager
        self.assertEqual(message_id, 90)
        self.assertEqual(owner.graph_id(10, 1), 90)
        self.assertEqual(owner.panel_id(10), 90)
        self.assertEqual(app._graph_cache_keys[1], (app.CHART_RANGE_2H, 2, 2))
        self.assertEqual(len(app.bot.photo_sends), 1)
        self.assertIs(owner._graph_refresh_callback, app._refresh_graph_message)
        owner._graph_refresh_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await owner._graph_refresh_task

    def test_active_graph_panel_hides_rd_release_control(self):
        app = FakeGraphApp()
        app.InlineKeyboardMarkup = InlineKeyboardMarkup
        original_builder = hmi.build_operator_keyboard
        try:
            hmi.build_operator_keyboard = lambda *_args, **_kwargs: InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="release", callback_data="rd_hands_off_release_confirm")],
                    [InlineKeyboardButton(text="pause", callback_data="operator_pause")],
                ]
            )
            markup = _active_graph_panel_markup(app, types.SimpleNamespace(), 1)
        finally:
            hmi.build_operator_keyboard = original_builder

        callbacks = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertNotIn("rd_hands_off_release_confirm", callbacks)
        self.assertIn("operator_pause", callbacks)

    async def test_range_change_edits_existing_graph_workspace(self):
        app = FakeGraphApp()
        call = types.SimpleNamespace(message=FakeGraphMessage())
        install_operator_graph_dashboard(app)
        await app._render_graph_workspace(app, call, 1)

        self.assertEqual(len(app.bot.media_edits), 1)
        self.assertEqual(app.bot.media_edits[0]["message_id"], 77)
        self.assertEqual(app.bot.media_edits[0]["media"]["caption"], "")
        self.assertEqual(call.message.answers, [])

    async def test_restore_dashboard_retires_stale_photo_identity_and_recreates_panel(self):
        app = FakeGraphApp()
        app.charge_controller.is_active = False
        app.user_dashboard = {1: 77}
        app.chat_dashboard = {10: 77}
        app.user_graph_dashboard = {1: 77}
        app.chat_graph_dashboard = {10: 77}
        app._graph_cache_keys = {1: ("2h", 10, 2)}
        app.operator_interface = types.SimpleNamespace(
            get_operator_snapshot=AsyncMock(return_value=object()),
            get_operator_actions=AsyncMock(return_value=None),
        )
        state = hmi.OperatorHmiState(
            hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE, "RD", False, "—", "",
            None, None, None, None, None, None, None, "", "OK",
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[])
        original_panel = hmi.render_operator_panel
        original_keyboard = hmi.build_operator_keyboard
        try:
            hmi.render_operator_panel = lambda _state: "control panel"
            hmi.build_operator_keyboard = lambda *_args, **_kwargs: markup
            with patch("operator_dashboard.OperatorSnapshotProvider.hmi_state_from_snapshot", return_value=state), \
                    patch("operator_dashboard._main_graph_markup", return_value=markup):
                install_operator_graph_dashboard(app)
                restored = await app._restore_dashboard_to_bottom(10, 1)
        finally:
            hmi.render_operator_panel = original_panel
            hmi.build_operator_keyboard = original_keyboard

        self.assertEqual(restored, 88)
        self.assertEqual(app.bot.deleted, [(10, 77)])
        self.assertEqual(app.user_dashboard[1], 88)
        self.assertEqual(app.chat_dashboard[10], 88)
        self.assertEqual(app.user_graph_dashboard, {})
        self.assertEqual(app.chat_graph_dashboard, {})
        self.assertEqual(app._graph_cache_keys, {})

    async def test_sixty_second_refresh_edits_existing_caption_without_new_graph_point(self):
        app = FakeGraphApp()
        app.user_graph_dashboard = {1: 77}
        app.chat_graph_dashboard = {10: 77}
        app.user_dashboard[1] = 77
        app.chat_dashboard[10] = 77
        app._graph_cache_keys = {1: (app.CHART_RANGE_2H, 2, 2)}
        app.operator_interface = types.SimpleNamespace(
            get_operator_snapshot=AsyncMock(return_value=object()),
            get_operator_actions=AsyncMock(return_value=None),
        )
        app.InlineKeyboardMarkup = InlineKeyboardMarkup
        state = hmi.OperatorHmiState(
            hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO, "RD",
            True, "CV", "EFB", 14.76, 0.23, 17.0, 26.0, 35.0, 14.8, 8.0, "", "OK",
        )
        refreshed = hmi.OperatorHmiState(
            hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO, "RD",
            True, "CV", "EFB", 14.76, 0.22, 17.0, 26.0, 35.0, 14.8, 8.0, "", "OK",
        )
        old_panel = hmi.render_operator_panel
        old_keyboard = hmi.build_operator_keyboard
        try:
            hmi.build_operator_keyboard = lambda *_args, **_kwargs: InlineKeyboardMarkup(inline_keyboard=[])
            with patch(
                "operator_dashboard.OperatorSnapshotProvider.hmi_state_from_snapshot",
                side_effect=[state, refreshed],
            ):
                install_operator_graph_dashboard(app)
                await app._refresh_graph_message(10, 1)
                await app._refresh_graph_message(10, 1)
        finally:
            hmi.render_operator_panel = old_panel
            hmi.build_operator_keyboard = old_keyboard

        self.assertEqual(len(app.bot.caption_edits), 2)
        self.assertEqual([x["message_id"] for x in app.bot.caption_edits], [77, 77])
        self.assertIn("0.23", app.bot.caption_edits[0]["caption"])
        self.assertIn("0.22", app.bot.caption_edits[1]["caption"])
        self.assertEqual(app.bot.media_edits, [])
        self.assertEqual(app.bot.deleted, [])
        self.assertEqual(app.user_graph_dashboard[1], 77)

    async def test_sixty_second_new_graph_point_edits_media_in_existing_message(self):
        app = FakeGraphApp()
        app.user_graph_dashboard = {1: 77}
        app.chat_graph_dashboard = {10: 77}
        app._graph_cache_keys = {1: (app.CHART_RANGE_2H, 1, 1)}
        old_panel = hmi.render_operator_panel
        old_keyboard = hmi.build_operator_keyboard
        try:
            hmi.build_operator_keyboard = lambda *_args, **_kwargs: InlineKeyboardMarkup(inline_keyboard=[])
            install_operator_graph_dashboard(app)
            await app._refresh_graph_message(10, 1)
        finally:
            hmi.render_operator_panel = old_panel
            hmi.build_operator_keyboard = old_keyboard
        self.assertEqual(len(app.bot.media_edits), 1)
        self.assertEqual(app.bot.media_edits[0]["chat_id"], 10)
        self.assertEqual(app.bot.media_edits[0]["message_id"], 77)
        self.assertEqual(app.bot.caption_edits, [])
        self.assertEqual(app.bot.deleted, [])
        self.assertEqual(app.user_graph_dashboard[1], 77)
        self.assertEqual(app._graph_cache_keys[1][1:], (2, 2))

    async def test_media_delivery_failure_preserves_graph_cache_key(self):
        app = FakeGraphApp()
        app.user_graph_dashboard = {1: 77}
        app.chat_graph_dashboard = {10: 77}
        previous_key = (app.CHART_RANGE_2H, 1, 1)
        app._graph_cache_keys = {1: previous_key}
        owner = TerminalPanelManager(app)
        app.terminal_panel_manager = owner
        app.bot.edit_message_media = AsyncMock(side_effect=RuntimeError("telegram unavailable"))
        original_keyboard = hmi.build_operator_keyboard
        try:
            hmi.build_operator_keyboard = lambda *_args, **_kwargs: InlineKeyboardMarkup(inline_keyboard=[])
            install_operator_graph_dashboard(app)
            await owner.refresh_graph(10, 1, app._refresh_graph_message)
        finally:
            hmi.build_operator_keyboard = original_keyboard
        self.assertEqual(app._graph_cache_keys[1], previous_key)
        app.bot.edit_message_media.assert_awaited_once()

    async def test_caption_message_not_modified_is_swallowed(self):
        app = FakeGraphApp()
        app.user_graph_dashboard = {1: 77}
        app.chat_graph_dashboard = {10: 77}
        key = (app.CHART_RANGE_2H, 2, 2)
        app._graph_cache_keys = {1: key}
        app.bot.edit_message_caption = AsyncMock(
            side_effect=RuntimeError("Bad Request: message is not modified")
        )
        owner = TerminalPanelManager(app)
        app.terminal_panel_manager = owner
        install_operator_graph_dashboard(app)
        await owner.refresh_graph(10, 1, app._refresh_graph_message)
        app.bot.edit_message_caption.assert_awaited_once()
        self.assertEqual(app._graph_cache_keys[1], key)

    async def test_stale_refresh_does_not_edit_replacement_graph_id(self):
        app = FakeGraphApp()
        app.user_graph_dashboard = {1: 77}
        app.chat_graph_dashboard = {10: 77}
        app._graph_cache_keys = {1: (app.CHART_RANGE_2H, 1, 1)}
        owner = TerminalPanelManager(app)
        app.terminal_panel_manager = owner

        async def graph_read(*, limit, since_timestamp):
            app.user_graph_dashboard[1] = 99
            app.chat_graph_dashboard[10] = 99
            return [1, 2], [13.0, 13.1], [1.0, 0.9], [25.0, 25.1]

        app.get_graph_data_with_temp = graph_read
        original_keyboard = hmi.build_operator_keyboard
        try:
            hmi.build_operator_keyboard = lambda *_args, **_kwargs: InlineKeyboardMarkup(inline_keyboard=[])
            install_operator_graph_dashboard(app)
            await owner.refresh_graph(10, 1, app._refresh_graph_message)
        finally:
            hmi.build_operator_keyboard = original_keyboard
        self.assertEqual(app.bot.media_edits, [])
        self.assertEqual(app._graph_cache_keys[1], (app.CHART_RANGE_2H, 1, 1))

    async def test_missing_graph_id_never_sends_refresh(self):
        app = FakeGraphApp()
        app.user_graph_dashboard = {}
        owner = TerminalPanelManager(app)
        app.terminal_panel_manager = owner
        install_operator_graph_dashboard(app)
        await owner.refresh_graph(10, 1, app._refresh_graph_message)
        self.assertEqual(app.bot.media_edits, [])
        self.assertEqual(app.bot.caption_edits, [])

    async def test_registered_refresh_owner_retires_graph_when_charge_inactive(self):
        app = FakeGraphApp()
        app.charge_controller.is_active = False
        app.user_graph_dashboard = {1: 77}
        app.chat_graph_dashboard = {10: 77}
        owner = TerminalPanelManager(app)
        app.terminal_panel_manager = owner
        install_operator_graph_dashboard(app)
        await owner.refresh_graph(10, 1, app._refresh_graph_message)
        self.assertEqual(app.bot.deleted, [(10, 77)])
        self.assertEqual(app.user_graph_dashboard, {})
        self.assertEqual(app.bot.media_edits, [])

    async def test_back_to_existing_graph_updates_caption_without_chart_rebuild(self):
        app = FakeGraphApp()
        app.user_graph_dashboard = {1: 77}
        app.chat_graph_dashboard = {10: 77}
        app.operator_interface = types.SimpleNamespace(
            get_operator_snapshot=AsyncMock(return_value=object()),
            get_operator_actions=AsyncMock(return_value=None),
        )
        app.InlineKeyboardMarkup = InlineKeyboardMarkup
        graph_read = AsyncMock(side_effect=AssertionError("back navigation must not rebuild history"))
        app.get_graph_data_with_temp = graph_read
        state = hmi.OperatorHmiState(
            hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO, "RD", True, "CV", "EFB",
            14.4, 1.2, 17.0, 25.0, 35.0, 14.8, 2.0, "", "OK",
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[])
        original_panel = hmi.render_operator_panel
        original_keyboard = hmi.build_operator_keyboard
        try:
            hmi.render_operator_panel = lambda _state: "panel caption"
            hmi.build_operator_keyboard = lambda *_args, **_kwargs: markup
            with patch("operator_dashboard.OperatorSnapshotProvider.hmi_state_from_snapshot", return_value=state):
                install_operator_graph_dashboard(app)
                refreshed = await app._refresh_operator_panel(10, 1, 77)
        finally:
            hmi.render_operator_panel = original_panel
            hmi.build_operator_keyboard = original_keyboard

        self.assertEqual(refreshed, 77)
        self.assertEqual(len(app.bot.caption_edits), 1)
        self.assertEqual(app.bot.caption_edits[0]["caption"], "panel caption")
        graph_read.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
