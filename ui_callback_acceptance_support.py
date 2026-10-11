"""Shared offline callback-dispatch scenarios for the UI acceptance gate.

The scenarios intentionally use only fake aiogram-shaped events.  They return
the installed handler objects that were actually invoked so callers cannot
turn filter matches into execution coverage by accident.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import production_bot_ui
import sg_ui
import manual_context
import mix_mode
import bot  # noqa: F401 - composition installs the canonical callbacks
from battery_registry import BatteryRecord
from application.operator_snapshot import snapshot_from_mapping
from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, BatteryLifecycle
from runtime import production_runtime as app
from runtime.ui.telegram.analysis import ANALYSIS_CALLBACK_DATA
from runtime.ui.telegram.custom import CUSTOM_CANCEL_CALLBACK_DATA
from runtime.ui.telegram.entities import ENTITIES_CALLBACK_DATA
from runtime.ui.telegram.journal import JOURNAL_CALLBACK_DATA
from runtime.ui.telegram.off_conditions import OFF_CALLBACK_DATA, OFF_PRESET_PREFIX


class FakeMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=104)
        self.message_id = 900
        self.answers: list[tuple[str, dict]] = []

    async def answer(self, text: str = "", **kwargs):
        self.answers.append((str(text), kwargs))
        return self

    async def edit_text(self, text: str = "", **kwargs):
        self.answers.append((str(text), kwargs))
        return self


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=104)
        self.message = FakeMessage()
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def acceptance_record() -> BatteryRecord:
    return BatteryRecord(
        identity=BatteryIdentity(
            "Leoch_72Ah", BatteryChemistry.EFB, 72,
            manufacturer="Leoch", model="DJW12-72",
        ),
        lifecycle=BatteryLifecycle(condition=BatteryCondition.UNKNOWN),
    )


async def _installed_handler(data: str):
    matches = []
    event = FakeCallback(data)
    for handler in app.router.observers["callback_query"].handlers:
        matched, _ = await handler.check(event)
        if matched:
            matches.append(handler)
    if len(matches) != 1:
        raise AssertionError(f"expected one installed handler for {data!r}, got {len(matches)}")
    return matches[0]


async def _dispatch(data: str, *, state: dict[int, object] | None = None):
    if state is not None:
        production_bot_ui._selected_battery[104] = state["record"]
        production_bot_ui._pending_profile[104] = "EFB"
    handler = await _installed_handler(data)
    call = FakeCallback(data)
    try:
        await asyncio.wait_for(handler.callback(call), timeout=2)
    except Exception as exc:
        raise AssertionError(f"callback {data!r} failed: {type(exc).__name__}: {exc}") from exc
    if not call.answers and not call.message.answers:
        raise AssertionError(f"callback {data!r} returned without callback ack or message response")
    return handler, call


async def exercise_safe_callbacks() -> list[dict[str, object]]:
    """Invoke the safe/read-only callback wave and return execution evidence."""
    production_bot_ui._battery_pages.clear()
    production_bot_ui._selected_battery.clear()
    production_bot_ui._pending_profile.clear()
    production_bot_ui._pending_intent.clear()
    production_bot_ui._pending_start.clear()
    app.awaiting_ah.clear()
    record = acceptance_record()
    exercised: list[dict[str, object]] = []
    fake_start_submit = AsyncMock(return_value=SimpleNamespace(
        accepted=False, reason="offline_safety_preflight_rejected", port_result=None,
    ))

    async def deny_output(*_args, **_kwargs):
        raise AssertionError("offline callback acceptance attempted a hardware output call")

    async def invoke(data: str, *, state: dict[int, object] | None = None) -> None:
        handler, call = await _dispatch(data, state=state)
        exercised.append({
            "callback": data,
            "module": handler.callback.__module__,
            "handler": handler.callback.__qualname__,
            "ack_count": len(call.answers),
            "message_response_count": len(call.message.answers),
        })

    with ExitStack() as stack:
        stack.enter_context(patch.object(app, "_check_chat_and_respond", new=AsyncMock(return_value=True)))
        stack.enter_context(patch.object(app.hass, "get_all_live", new=AsyncMock(return_value={
            "battery_voltage": "12.7", "current": "0.0", "temp_ext": "22", "switch": "off",
        })))
        stack.enter_context(patch.object(app.charge_controller, "ui_support_snapshot", return_value=SimpleNamespace()))
        stack.enter_context(patch.object(production_bot_ui, "format_active_evidence", return_value="offline evidence"))
        stack.enter_context(patch.object(production_bot_ui, "list_batteries", new=AsyncMock(return_value=[])))
        stack.enter_context(patch.object(manual_context, "list_batteries", new=AsyncMock(return_value=[])))
        stack.enter_context(patch.object(mix_mode, "list_batteries", new=AsyncMock(return_value=[record])))
        stack.enter_context(patch.object(sg_ui, "set_sg_access", new=AsyncMock()))
        stack.enter_context(patch.object(sg_ui, "list_batteries", new=AsyncMock(return_value=[record])))
        stack.enter_context(patch.object(sg_ui, "get_sg_access", new=AsyncMock(return_value=sg_ui.SGAccess.INACCESSIBLE)))
        stack.enter_context(patch.object(production_bot_ui, "_resolve_battery_callback", new=AsyncMock(return_value=record)))
        stack.enter_context(patch.object(production_bot_ui, "_route_profile_intent", new=AsyncMock(return_value=True)))
        stack.enter_context(patch.object(production_bot_ui, "_refresh_dashboard_after_selection", new=AsyncMock()))
        stack.enter_context(patch.object(app, "schedule_dashboard_after_60", lambda *_args: None))
        stack.enter_context(patch.object(app, "_build_ai_analysis_text", new=AsyncMock(return_value="offline analysis")))
        stack.enter_context(patch.object(app, "get_raw_history", new=AsyncMock(return_value=([], [], []))))
        stack.enter_context(patch.object(app, "get_recent_events", return_value=[]))
        stack.enter_context(patch.object(app, "ask_deepseek", new=AsyncMock(return_value="offline")))
        stack.enter_context(patch.object(app, "_format_manual_off_for_dashboard", return_value="OFF"))
        stack.enter_context(patch.object(
            app, "_v3_production_start_route",
            SimpleNamespace(submit=fake_start_submit),
        ))
        stack.enter_context(patch.object(app.hass, "safe_enable_output", new=deny_output))
        control_manager = getattr(bot._composition, "rd_control_mode", None)
        if control_manager is not None:
            stack.enter_context(patch.object(control_manager, "return_pb_control", new=AsyncMock(return_value=None)))

        # Keep the acceptance focused on callback dispatch/ack semantics.  The
        # screen builders themselves have separate unit coverage and these
        # patches prevent a fake snapshot shape from becoming a false route
        # failure.
        for module in (
            "runtime.ui.telegram.charge", "runtime.ui.telegram.details",
            "runtime.ui.telegram.service", "runtime.ui.telegram.entities",
            "runtime.ui.telegram.analysis", "runtime.ui.telegram.journal",
            "runtime.ui.telegram.off_conditions",
        ):
            stack.enter_context(patch(f"{module}.render_screen_text", return_value="offline screen"))
            stack.enter_context(patch(f"{module}.render_screen_markup", return_value=None))
        stack.enter_context(patch("runtime.ui.telegram.details.build_operator_details_screen", return_value=SimpleNamespace()))
        stack.enter_context(patch("runtime.ui.telegram.service.build_service_details_screen", return_value=SimpleNamespace()))
        stack.enter_context(patch("runtime.ui.telegram.entities.build_entities_screen", return_value=SimpleNamespace()))
        stack.enter_context(patch("runtime.ui.telegram.journal.build_journal_screen", return_value=SimpleNamespace()))
        stack.enter_context(patch("runtime.ui.telegram.analysis.build_analysis_screen", return_value=SimpleNamespace()))
        stack.enter_context(patch("runtime.ui.telegram.off_conditions.build_off_conditions_screen", return_value=SimpleNamespace()))

        interface = bot._composition.operator_interface
        for method in (
            "get_operator_details", "get_service_details", "get_entity_statuses", "get_event_journal",
        ):
            stack.enter_context(patch.object(interface, method, new=AsyncMock(return_value=SimpleNamespace())))
        stack.enter_context(patch.object(type(interface), "get_entity_statuses", new=AsyncMock(return_value=SimpleNamespace())))
        stack.enter_context(patch.object(interface, "submit_intent", new=AsyncMock(
            return_value=SimpleNamespace(status="accepted", reason="offline")
        )))
        fake_operator_snapshot = snapshot_from_mapping({
            "state": "IDLE",
            "charge": {"stage": "IDLE", "program": "", "phase": "OFF"},
            "telemetry": {"voltage": 12.7, "current": 0.0, "temperature": 22.0},
            "output": {"enabled": False, "power_w": 0.0},
            "safety": {"allowed": True, "reason": "offline"},
        })
        stack.enter_context(patch.object(interface, "get_operator_snapshot", new=AsyncMock(return_value=fake_operator_snapshot)))
        stack.enter_context(patch.object(app, "_refresh_operator_panel", new=AsyncMock()))
        stack.enter_context(patch.object(app, "_build_and_send_dashboard", new=AsyncMock()))
        stack.enter_context(patch("operator_hmi._render_graph_workspace", new=AsyncMock()))
        stack.enter_context(patch.object(app, "_operator_pause_toggle", new=AsyncMock()))
        stack.enter_context(patch.object(app, "_operator_pause_active", return_value=False))

        # V2 home/charge/battery/profile/intent routes.
        await invoke("v2_status")
        await invoke("v2_batteries")
        await invoke("v2_battery_add")
        await invoke("v2_battery_id_000000000000", state={"record": record})
        await invoke("v2_profile_efb")
        for intent in ("normal", "recovery", "conditioning", "diagnostic"):
            await invoke(f"v2_quick_intent_{intent}")
        for intent in ("normal", "recovery", "conditioning", "diagnostic"):
            await invoke(f"v2_bat_intent_{intent}", state={"record": record})
        # The retired callback must remain unhandled; only the current Manual
        # identity-choice callback is dispatched through the installed router.
        if any(
            (await candidate.check(FakeCallback("v2_manual")))[0]
            for candidate in app.router.observers["callback_query"].handlers
        ):
            raise AssertionError("retired v2_manual callback must have no matching handler")
        for data in ("v2_manual_choose", "v2_manual_unbound", "v2_manual_interrupted"):
            await invoke(data, state={"record": record})
        await invoke("v2_quick_start")
        await invoke("v2_battery_start")
        await invoke("v2_sg_menu")
        await invoke("v2_sg_pick_0")
        # SG access choices and Mix previews are read-only UX/state preparation;
        # their physical execution callbacks remain outside this acceptance wave.
        sg_ui._pending_sg_battery[104] = record
        await invoke("v2_sg_access_serviceable")
        sg_ui._pending_sg_battery[104] = record
        await invoke("v2_sg_access_inaccessible")
        await invoke("v2_mix")
        await invoke("v2_mix_profile_efb")
        await invoke("v2_mix_bat_0")
        if fake_start_submit.await_count != 2:
            raise AssertionError("FAKE START preflight did not reject without actuator output")
        await invoke("rd_hands_off_disable")
        await invoke("rd_autonomous_cancel")
        await invoke("operator_adopted_stop")
        await invoke("operator_managed_mix_stop")
        await invoke("rd_managed_mix_status")

        # Canonical V3 charge/navigation and read-only screens.
        for data in (
            "ui:nav.charge", "ui:charge.select_profile?profile=EFB", "ui:nav.batteries",
            "ui:nav.battery_add", "ui:nav.manual", "ui:nav.manual_interrupted",
            "ui:nav.diagnostics", "ui:nav.service",
        ):
            await invoke(data, state={"record": record})
        # Wave 3: every remaining read-only V3 screen and operator navigation
        # route is invoked through the installed handler, with fake providers.
        for data in (
            CUSTOM_CANCEL_CALLBACK_DATA,
            "ui:nav.home",
            JOURNAL_CALLBACK_DATA,
            OFF_CALLBACK_DATA,
            f"{OFF_PRESET_PREFIX}?preset=time_2h",
            ENTITIES_CALLBACK_DATA,
            ANALYSIS_CALLBACK_DATA,
            "operator_done",
            "operator_graph",
            "operator_graph_30m",
            "operator_refresh",
            "operator_more",
            "operator_pause_toggle",
        ):
            await invoke(data, state={"record": record})
    # Some legacy read helpers schedule best-effort background work.  This is
    # an offline acceptance process, so cancel anything it spawned before the
    # event loop is closed; no task may outlive the fake Telegram session.
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=2)
        except asyncio.TimeoutError as exc:
            raise AssertionError("offline callback acceptance left a task running after cancellation") from exc
    return exercised
