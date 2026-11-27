"""Declarative operator navigation layouts; rendering stays in Telegram."""
from __future__ import annotations

from typing import Any

from runtime.ui.telegram.analysis import ANALYSIS_CALLBACK_DATA
from runtime.ui.telegram.renderer import render_callback_rows
from runtime.ui.labels.operator_actions import MANAGED_MIX_STATUS_BUTTON
from .hmi_state import OperatorHmiState, HmiProcessState


def _back_keyboard():
    return render_callback_rows([[("⬅ К панели", "operator_done")]])


def _graph_keyboard(app: Any, user_id: int):
    selected = str(app._chart_range_for_user(user_id))

    def button(mode: str, label: str) -> tuple[str, str]:
        marker = "● " if selected == mode else ""
        return (f"{marker}{label}", f"operator_graph_{mode}")

    return render_callback_rows([[
        button(app.CHART_RANGE_30M, "30м"),
        button(app.CHART_RANGE_2H, "2ч"),
        button(app.CHART_RANGE_SESSION, "Сессия"),
    ]])


def _more_keyboard(state: OperatorHmiState, app: Any = None):
    from runtime.optional_modules import optional_ui_enabled
    manager = getattr(app, "_optional_modules", None) if app is not None else None
    ai_visible = (
        manager.installed("ai")
        if manager is not None
        else optional_ui_enabled("ai")
    )
    rows: list[list[tuple[str, str]]] = (
        [[("🧠 AI анализ", ANALYSIS_CALLBACK_DATA)]] if ai_visible else []
    )
    if state.process_state is HmiProcessState.IDLE:
        rows.append([("🛠 Ручной режим", "v2_manual_choose")])
        rows.append([("🔋 АКБ", "v2_batteries")])
    if state.process_state is HmiProcessState.ADOPTED_MIX:
        rows.append([("🧲 Статус Mix", "rd_live_mix_status")])
        coordinator = getattr(app, "rd_managed_mix_adoption", None) if app is not None else None
        if coordinator is not None and (
            bool(getattr(coordinator, "active", False)) or bool(getattr(coordinator, "off_pending", False))
        ):
            rows[-1] = [MANAGED_MIX_STATUS_BUTTON]
    if state.process_state is HmiProcessState.HANDS_OFF and not state.output_on:
        rows.append([("🔒 Вернуть Pb-контроль", "rd_hands_off_disable")])
    rows.append([("⬅ К панели", "operator_done")])
    return render_callback_rows(rows)


def chart_range_for_user(app: Any, user_id: int, *, now_s: float | None = None) -> str:
    """Resolve the legacy chart window from explicit operator/session state."""
    import time

    manual_mode = app.user_chart_range.get(user_id)
    if manual_mode in app.CHART_RANGE_VALUES:
        return manual_mode

    controller = app.charge_controller
    if bool(getattr(controller, "is_active", False)) and getattr(controller, "total_start_time", 0):
        now_value = time.time() if now_s is None else float(now_s)
        elapsed_sec = max(0.0, now_value - float(controller.total_start_time))
        if elapsed_sec < 2 * 3600:
            return app.CHART_RANGE_30M
        if elapsed_sec <= 8 * 3600:
            return app.CHART_RANGE_2H
        return app.CHART_RANGE_SESSION

    return app.CHART_RANGE_DEFAULT


def chart_label(app: Any, mode: str) -> str:
    return {
        app.CHART_RANGE_30M: "30м",
        app.CHART_RANGE_2H: "2ч",
        app.CHART_RANGE_SESSION: "Сессия",
    }.get(mode, "2ч")


def chart_query_params(app: Any, user_id: int, *, now_s: float | None = None) -> tuple:
    """Return the existing chart query window without owning chart/session state."""
    import time

    now_value = time.time() if now_s is None else float(now_s)
    mode = chart_range_for_user(app, user_id, now_s=now_value)
    if mode == app.CHART_RANGE_30M:
        return mode, now_value - 30 * 60, 120
    controller = app.charge_controller
    if (
        mode == app.CHART_RANGE_SESSION
        and bool(getattr(controller, "is_active", False))
        and getattr(controller, "total_start_time", None)
    ):
        return mode, controller.total_start_time, 500
    if mode == app.CHART_RANGE_SESSION:
        mode = app.CHART_RANGE_2H
    return mode, now_value - 2 * 3600, 300
