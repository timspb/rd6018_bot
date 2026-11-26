from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from application.operator_snapshot_provider import (
    OperatorSnapshotProvider,
    build_ai_analysis_text,
    build_ai_context_dict,
    build_ai_context_text,
    build_trend_summary,
)
from application.operator_read_source import OperatorReadSource
from application.operator_snapshot import snapshot_from_mapping


class _Hass:
    def __init__(self, live):
        self.live = live

    async def get_all_live(self):
        return self.live


class _SequencedHass:
    def __init__(self, *values):
        self.values = list(values)
        self.reads = 0

    async def get_all_live(self):
        value = self.values[min(self.reads, len(self.values) - 1)]
        self.reads += 1
        return value


class _Controller:
    is_active = False


class _App:
    charge_controller = _Controller()
    manual_session_manager = None
    rd_control_mode_manager = None
    rd_live_mix_observer = None

    def __init__(self, live):
        self.hass = _Hass(live)

    def _operator_pause_active(self):
        return False


class _HandsOffManager:
    hands_off = True


def live(**overrides):
    value = {
        "switch": "off", "battery_voltage": 12.8, "current": 0.0,
        "power": 0.0, "temp_ext": 25.0, "temp_int": 30.0,
        "protection_code": 0,
        "ovp_triggered": "off", "ocp_triggered": "off",
        "is_cc": "off", "is_cv": "off",
        "_freshness": {name: 0.0 for name in ("switch", "battery_voltage", "current", "protection_code", "regulation_code")},
    }
    value.update(overrides)
    return value


class OperatorSnapshotProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_snapshot_renderer_preserves_manual_authority_and_psu_temperature(self):
        snapshot = snapshot_from_mapping({
            "state": "CHARGING",
            "charge": {"stage": "Main Charge", "program": "manual", "phase": "CV", "waiting_for": "internal"},
            "telemetry": {"voltage": 13.55, "current": 1.46, "temperature": 23.0, "psu_temperature": 33.0},
            "output": {"enabled": True},
        })
        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        self.assertEqual(state.authority.value, "manual")
        self.assertEqual(state.psu_temp_c, 33.0)
        self.assertEqual(state.progress, "")
    async def test_one_live_snapshot_retains_paused_and_running_control_actions(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from operator_hmi import HmiProcessState, HmiAuthority
        from application.operator_actions import OperatorAction
        for process, expected in (
            (HmiProcessState.RUNNING, OperatorAction.PAUSE_CHARGE),
            (HmiProcessState.PAUSED, OperatorAction.RESUME_CHARGE),
        ):
            with self.subTest(process=process):
                app = _App(live())
                app._operator_pause_state = SimpleNamespace(active=lambda: process is HmiProcessState.PAUSED)
                app._operator_pause_active = lambda: self.fail("read model must not invoke authority-retiring pause wrapper")
                app.hass = _SequencedHass(live(), live(switch="on"))
                source = OperatorReadSource(app)
                state = SimpleNamespace(
                    process_state=process, authority=HmiAuthority.AUTO,
                    output_on=True, regulator="CV", title="MAIN",
                    manual_interrupted=False, attention="normal", safety="ok",
                )
                with patch.object(source, "hmi_state", return_value=state):
                    provider = OperatorSnapshotProvider(source)
                    snapshot = await provider.get_operator_snapshot()
                    actions = await provider.get_operator_actions(snapshot=snapshot)
                self.assertEqual(app.hass.reads, 1)
                self.assertEqual(snapshot.process_state, process.value)
                self.assertEqual(snapshot.state, "CHARGING")
                self.assertEqual(
                    {item.action.value for item in actions.available_actions},
                    set(snapshot.available_actions),
                )
                self.assertIn(expected, {item.action for item in actions.available_actions})
                self.assertEqual(provider.hmi_state_from_snapshot(snapshot).process_state, process)

    async def test_read_source_pause_state_is_pure_and_does_not_call_retirement_wrapper(self):
        from types import SimpleNamespace

        app = _App(live())
        app._operator_pause_state = SimpleNamespace(active=lambda: True)
        app._operator_pause_active = lambda: self.fail("read source must not retire pause state")
        self.assertTrue(OperatorReadSource(app).pause_active())

    async def test_read_source_suppresses_stale_pause_display_in_hands_off_mode(self):
        from types import SimpleNamespace

        app = _App(live())
        app.rd_control_mode_manager = _HandsOffManager()
        app._operator_pause_state = SimpleNamespace(active=lambda: True)
        self.assertFalse(OperatorReadSource(app).pause_active())

    async def test_idle_snapshot_is_read_only_and_maps_actions(self):
        provider = OperatorSnapshotProvider(OperatorReadSource(_App(live())))
        snapshot = await provider.get_operator_snapshot()
        self.assertEqual(snapshot.state, "IDLE")
        self.assertIn("start_charge", snapshot.available_actions)
        self.assertFalse(hasattr(snapshot, "hass"))

    async def test_interrupted_manual_survives_snapshot_to_real_buttons(self):
        from types import SimpleNamespace
        from operator_hmi import build_operator_keyboard
        from application.operator_actions import OperatorAction
        app = _App(live())
        app.manual_session_manager = SimpleNamespace(
            is_active=False, state=SimpleNamespace(value="interrupted"),
            battery_id="China",
        )
        app.hass = _SequencedHass(live(), live(switch="on"))
        provider = OperatorSnapshotProvider(OperatorReadSource(app))
        snapshot = await provider.get_operator_snapshot()
        actions = await provider.get_operator_actions(snapshot=snapshot)
        restored = provider.hmi_state_from_snapshot(snapshot)
        self.assertEqual(snapshot.state, "IDLE")
        self.assertTrue(snapshot.manual_interrupted)
        self.assertTrue(restored.manual_interrupted)
        self.assertEqual(app.hass.reads, 1)
        self.assertEqual(
            {item.action for item in actions.available_actions},
            {OperatorAction.REAUTHORIZE_MANUAL, OperatorAction.DISCARD_MANUAL},
        )
        self.assertEqual(
            set(snapshot.available_actions),
            {"reauthorize_manual", "discard_manual"},
        )
        callbacks = [
            item.callback_data
            for row in build_operator_keyboard(app, restored, actions=actions).inline_keyboard
            for item in row
        ]
        self.assertIn("v2_manual_reauthorize", callbacks)
        self.assertIn("v2_manual_discard", callbacks)
        self.assertNotIn("ui:nav.charge", callbacks)

    async def test_snapshot_manual_interrupted_requires_actual_flag(self):
        from application.operator_actions import OperatorAction
        provider = OperatorSnapshotProvider(OperatorReadSource(_App(live())))
        snapshot = snapshot_from_mapping({
            "state": "IDLE",
            "manual_interrupted": False,
            "output": {"enabled": False},
        })
        actions = await provider.get_operator_actions(snapshot=snapshot)
        self.assertNotIn(
            OperatorAction.REAUTHORIZE_MANUAL,
            {item.action for item in actions.available_actions},
        )

    async def test_stale_telemetry_is_fault_and_start_is_removed(self):
        old = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        data = live(_meta={name: {"status": "ok", "last_reported": old} for name in ("switch", "battery_voltage", "current", "protection_code", "regulation_code")})
        snapshot = await OperatorSnapshotProvider(OperatorReadSource(_App(data))).get_operator_snapshot()
        self.assertEqual(snapshot.state, "FAULT")
        self.assertNotIn("start_charge", snapshot.available_actions)
        self.assertFalse(snapshot.telemetry_fresh)

    async def test_idle_actions_reuse_home_snapshot_across_telemetry_refresh_race(self):
        fresh = live()
        old = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        stale = live(_meta={name: {"status": "ok", "last_reported": old} for name in (
            "switch", "battery_voltage", "current", "protection_code", "regulation_code"
        )})
        app = _App(fresh)
        app.hass = _SequencedHass(fresh, stale)
        provider = OperatorSnapshotProvider(OperatorReadSource(app))

        snapshot = await provider.get_operator_snapshot()
        actions = await provider.get_operator_actions(snapshot=snapshot)

        self.assertEqual(snapshot.state, "IDLE")
        self.assertTrue(snapshot.snapshot.safety.allowed)
        self.assertIn("start_charge", {item.action.value for item in actions.available_actions})
        self.assertEqual(app.hass.reads, 1)

    async def test_hands_off_snapshot_preserves_exact_progress_and_does_not_reread(self):
        first = live()
        second = live(switch="on", battery_voltage=15.2, current=2.4)
        app = _App(first)
        app.rd_control_mode_manager = _HandsOffManager()
        app.hass = _SequencedHass(first, second)
        provider = OperatorSnapshotProvider(OperatorReadSource(app))

        snapshot = await provider.get_operator_snapshot()
        actions = await provider.get_operator_actions(snapshot=snapshot)
        state = provider.hmi_state_from_snapshot(snapshot)

        self.assertEqual(snapshot.state, "HANDS_OFF")
        self.assertEqual(state.process_state.value, "hands_off")
        self.assertEqual(state.progress, "RD свободен от Pb-автоматики")
        self.assertEqual(app.hass.reads, 1)
        callbacks = {item.action.value for item in actions.available_actions}
        self.assertEqual(callbacks, {"start_charge", "return_pb_control"})
        self.assertNotIn("stop_charge", callbacks)
        self.assertNotIn("disable_output", callbacks)

    async def test_idle_navigation_remains_visible_for_safety_denied_read_model(self):
        snapshot = snapshot_from_mapping({
            "state": "IDLE",
            "safety": {"allowed": False, "reason": "telemetry_stale"},
            "output": {"enabled": False},
            "charge": {"stage": "IDLE"},
        })
        provider = OperatorSnapshotProvider(OperatorReadSource(_App(live())))
        actions = await provider.get_operator_actions(snapshot=snapshot)
        self.assertIn("start_charge", {item.action.value for item in actions.available_actions})

    async def test_fault_mapping(self):
        snapshot = await OperatorSnapshotProvider(OperatorReadSource(_App(live(protection_code=3)))).get_operator_snapshot()
        self.assertEqual(snapshot.state, "FAULT")
        self.assertIn("⚠️ Защита сработала", snapshot.faults)

    async def test_details_and_service_details_are_dtos(self):
        provider = OperatorSnapshotProvider(OperatorReadSource(_App(live())))
        details = await provider.get_operator_details()
        service = await provider.get_service_details()
        self.assertEqual(details.process_state, "idle")
        self.assertEqual(service.output_on, False)
        self.assertFalse(hasattr(details, "hass"))
        self.assertFalse(hasattr(service, "controller"))

    async def test_ai_context_projection_uses_one_explicit_live_read(self):
        app = _App(live(switch="on", battery_voltage=13.2, current=1.5, temp_ext=24.0, temp_int=31.0))
        app.hass = _SequencedHass(app.hass.live)
        app.charge_controller = type("Controller", (), {
            "ah_capacity": 72,
            "current_stage": "Main Charge",
            "battery_type": "EFB",
        })()
        source = OperatorReadSource(app)
        result = await build_ai_context_dict(
            source,
            stage_snapshot=lambda temp: {
                "stage": "Main Charge", "profile": "EFB", "phase": "CV",
                "timers": {"remaining_time": "01:00:00"},
            },
        )
        self.assertEqual(app.hass.reads, 1)
        self.assertEqual(result["output_status"], "ON")
        self.assertEqual(result["capacity_ah"], 72)
        self.assertEqual(result["current_stage"], "Main Charge")
        self.assertEqual(result["mode"], "CV")
        self.assertEqual(result["v_batt_now"], 13.2)

    async def test_ai_context_projection_fails_closed_to_legacy_unknown_shape(self):
        source = OperatorReadSource(_App(live()))
        source.read_live = AsyncMock(side_effect=RuntimeError("offline"))
        result = await build_ai_context_dict(source, stage_snapshot=lambda temp: {})
        self.assertEqual(result["output_status"], "UNKNOWN")
        self.assertEqual(result["capacity_ah"], "UNKNOWN")
        self.assertFalse(result["capacity_known"])
        self.assertIsNone(result["v_batt_now"])

    async def test_ai_context_text_preserves_single_live_read_and_event_windows(self):
        app = _App(live(
            switch="on", battery_voltage=13.2, voltage=14.1, current=1.5,
            power=21.15, ah=4.2, wh=58.0, set_voltage=14.7, set_current=7.2,
            temp_ext=24.0, temp_int=31.0, input_voltage=60.0, uptime="01:23:45",
            is_cv=True, is_cc=False,
        ))
        app.hass = _SequencedHass(app.hass.live)
        app.charge_controller = type("Controller", (), {
            "is_active": True, "ah_capacity": 72,
            "current_stage": "Main Charge", "battery_type": "EFB",
            "get_timers": lambda self: {
                "total_time": "02:00:00", "stage_time": "01:00:00",
                "remaining_time": "01:00:00",
            },
        })()
        calls = []
        def events(limit):
            calls.append(limit)
            return [f"event-{limit}"]
        result = await build_ai_context_text(
            OperatorReadSource(app),
            stage_snapshot=lambda temp: {"stage": "Main Charge"},
            recent_events=events,
            format_stage_snapshot=lambda snapshot: "strategy-card",
            format_events=lambda rows, limit: f"important-{limit}",
            canonical_bool=lambda live, key: live.get(key) is True,
        )
        self.assertEqual(app.hass.reads, 1)
        self.assertEqual(calls, [8, 5])
        self.assertIn("Статус выхода: ON", result)
        self.assertIn("Емкость АКБ: 72 Ач", result)
        self.assertIn("strategy-card", result)
        self.assertIn("important-8", result)
        self.assertIn("- event-5", result)

    async def test_ai_context_text_preserves_legacy_error_surface(self):
        source = OperatorReadSource(_App(live()))
        source.read_live = AsyncMock(side_effect=RuntimeError("offline"))
        result = await build_ai_context_text(
            source,
            stage_snapshot=lambda temp: {},
            recent_events=lambda limit: [],
            format_stage_snapshot=lambda snapshot: "",
            format_events=lambda rows, limit: "",
            canonical_bool=lambda live, key: live.get(key) is True,
        )
        self.assertEqual(result, "Ошибка получения AI контекста: offline")

    async def test_ai_analysis_projection_builds_legacy_payload_once(self):
        app = _App(live(switch="on", battery_voltage=13.4, current=1.1, temp_ext=25.0, temp_int=32.0, is_cv=True, is_cc=False))
        app.hass = _SequencedHass(app.hass.live)
        app.charge_controller = type("Controller", (), {
            "is_active": True, "ah_capacity": 72,
            "current_stage": "Main Charge", "battery_type": "EFB",
            "get_timers": lambda self: {"remaining_time": "00:45:00"},
        })()
        payloads = []
        async def ask(payload):
            payloads.append(payload)
            return "**OK**"
        result = await build_ai_analysis_text(
            OperatorReadSource(app),
            raw_history=lambda limit: (["t1"], [13.1], [1.2]),
            trend_summary=lambda times, volts, amps: "trend",
            stage_snapshot=lambda temp: {"stage": "Main Charge"},
            recent_events=lambda limit: ["event"],
            ask_ai=ask,
            render_ai_text=lambda text: "rendered:" + text,
            canonical_bool=lambda live, key: live.get(key) is True,
        )
        self.assertEqual(app.hass.reads, 1)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["trend_summary"], "trend")
        self.assertEqual(payloads[0]["ai_context"]["capacity_ah"], 72)
        self.assertEqual(payloads[0]["ai_context"]["mode"], "CV")
        self.assertEqual(payloads[0]["controller_snapshot"]["stage"], "Main Charge")
        self.assertEqual(result, "<b>🧠 AI Анализ</b>\nrendered:**OK**")

    def test_trend_summary_projection_preserves_legacy_sampling_and_labels(self):
        from datetime import datetime
        result = build_trend_summary(
            ["2026-11-14T11:00:00", "2026-11-14T11:20:00", "2026-11-14T11:40:00", "2026-11-14T12:00:00"],
            [13.0, 13.5, 14.0, 14.4],
            [2.0, 1.5, 1.0, 0.5],
            now=datetime(2026, 11, 14, 12, 0, 0),
        )
        self.assertEqual(
            result,
            "60 мин назад: 13.00В, 2.00А | 40 мин назад: 13.50В, 1.50А | "
            "20 мин назад: 14.00В, 1.00А | сейчас: 14.40В, 0.50А",
        )

    async def test_ai_analysis_projection_fails_closed(self):
        source = OperatorReadSource(_App(live()))
        source.read_live = AsyncMock(side_effect=RuntimeError("offline"))
        warnings = []
        result = await build_ai_analysis_text(
            source,
            raw_history=lambda limit: ([], [], []),
            trend_summary=lambda *args: "",
            stage_snapshot=lambda temp: {},
            recent_events=lambda limit: [],
            ask_ai=lambda payload: "unused",
            render_ai_text=lambda text: text,
            canonical_bool=lambda live, key: False,
            on_error=lambda exc: warnings.append(type(exc).__name__),
        )
        self.assertEqual(warnings, ["RuntimeError"])
        self.assertIn("Сервис временно недоступен", result)


if __name__ == "__main__":
    unittest.main()
