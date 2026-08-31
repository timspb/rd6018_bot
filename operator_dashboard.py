from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional

import operator_hmi as hmi


_UNKNOWN = {"", "unknown", "unavailable", "none", "null"}
_BASE_BUILD_OPERATOR_HMI_STATE = hmi.build_operator_hmi_state
_BASE_RENDER_OPERATOR_PANEL = hmi.render_operator_panel
_BASE_RENDER_OPERATOR_DETAILS = hmi.render_operator_details


def _binary(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in {"on", "true", "1"}:
        return True
    if raw in {"off", "false", "0"}:
        return False
    if raw in _UNKNOWN:
        return None
    return None


def build_truthful_hmi_state(
    app: Any,
    live: Mapping[str, Any],
    *,
    base_builder=None,
) -> hmi.OperatorHmiState:
    """Fail truthful at the presentation boundary without inventing actuator state.

    Runtime safety already fails closed on missing/unknown critical telemetry. The HMI
    must do the same semantically: an unknown Output is not OFF, and unavailable
    protection status is not "normal".
    """
    builder = base_builder or _BASE_BUILD_OPERATOR_HMI_STATE
    state = builder(app, live)
    output_state = _binary(live.get("switch"))

    if output_state is None:
        return replace(
            state,
            process_state=hmi.HmiProcessState.CONTAINMENT,
            authority=hmi.HmiAuthority.CONTAINMENT,
            title="RD6018 · OUTPUT НЕ ПОДТВЕРЖДЁН",
            output_on=False,
            progress="Физическое состояние Output неизвестно · новые команды запуска недоступны",
            safety="⚠️ Требуется восстановить достоверную телеметрию RD6018",
            attention="output_unknown",
        )

    ovp_state = _binary(live.get("ovp_triggered"))
    ocp_state = _binary(live.get("ocp_triggered"))
    if ovp_state is None or ocp_state is None:
        return replace(
            state,
            safety="⚠️ Статус защит RD6018 не подтверждён",
            attention="alarm" if output_state else "warning",
        )

    return state


def render_truthful_panel(
    state: hmi.OperatorHmiState,
    *,
    base_renderer=None,
) -> str:
    renderer = base_renderer or _BASE_RENDER_OPERATOR_PANEL
    text = renderer(state)
    if state.attention == "output_unknown":
        text = text.replace("Output <b>OFF</b>", "Output <b>UNKNOWN</b>", 1)
    return text


def render_truthful_details(
    app: Any,
    state: hmi.OperatorHmiState,
    live: Mapping[str, Any],
    *,
    base_renderer=None,
) -> str:
    renderer = base_renderer or _BASE_RENDER_OPERATOR_DETAILS
    text = renderer(app, state, live)
    if state.attention == "output_unknown":
        text = text.replace("Output: OFF", "Output: UNKNOWN", 1)
    return text


def install_operator_graph_dashboard(app: Any) -> None:
    """Keep the L2 graph while the semantic HMI owns caption and controls.

    This replaces only presentation transport. It does not add actuator authority.
    Graph data comes from the existing recorder/database path and the selected user
    range; semantic state is derived from the same fresh HA live snapshot.
    """
    if bool(getattr(app, "_operator_graph_dashboard_installed", False)):
        return

    base_builder = hmi.build_operator_hmi_state
    base_panel_renderer = hmi.render_operator_panel
    base_details_renderer = hmi.render_operator_details

    def truthful_builder(app_arg: Any, live: Mapping[str, Any]) -> hmi.OperatorHmiState:
        return build_truthful_hmi_state(app_arg, live, base_builder=base_builder)

    def truthful_panel(state: hmi.OperatorHmiState) -> str:
        return render_truthful_panel(state, base_renderer=base_panel_renderer)

    def truthful_details(app_arg: Any, state: hmi.OperatorHmiState, live: Mapping[str, Any]) -> str:
        return render_truthful_details(
            app_arg,
            state,
            live,
            base_renderer=base_details_renderer,
        )

    # operator_hmi handlers resolve these globals at call time, so details and the
    # compact caption inherit the same truthful UNKNOWN semantics.
    hmi.build_operator_hmi_state = truthful_builder
    hmi.render_operator_panel = truthful_panel
    hmi.render_operator_details = truthful_details

    async def build_and_send_graph_dashboard(
        chat_id: int,
        user_id: int,
        old_msg_id: Optional[int] = None,
        anchor_msg_id: Optional[int] = None,
    ) -> int:
        try:
            live = await app.hass.get_all_live()
        except Exception as exc:
            app.logger.error("Failed to get HA data for operator dashboard: %s", exc)
            live = {}

        state = truthful_builder(app, live)
        caption = truthful_panel(state)
        markup = hmi.build_operator_keyboard(app, state)

        photo = None
        try:
            _chart_mode, graph_since, limit_pts = app._chart_query_params(user_id)
            times, voltages, currents, temps = await app.get_graph_data_with_temp(
                limit=limit_pts,
                since_timestamp=graph_since,
            )
            buf = await app.asyncio.to_thread(
                app.generate_chart,
                times,
                voltages,
                currents,
                temps,
            )
            if buf:
                photo = app.BufferedInputFile(buf.getvalue(), filename="chart.png")
        except Exception as exc:
            # Losing history/graph rendering must never hide the live operator state.
            app.logger.warning("operator dashboard graph unavailable: %s", exc)

        target = old_msg_id or anchor_msg_id
        if target:
            try:
                if photo:
                    await app.bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=target,
                        media=app.InputMediaPhoto(
                            media=photo,
                            caption=caption,
                            parse_mode=app.ParseMode.HTML,
                        ),
                        reply_markup=markup,
                    )
                else:
                    await app.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=target,
                        text=caption,
                        reply_markup=markup,
                        parse_mode=app.ParseMode.HTML,
                    )
                app.user_dashboard[user_id] = target
                app.chat_dashboard[chat_id] = target
                return int(target)
            except Exception as exc:
                if "message is not modified" in str(exc).lower():
                    app.user_dashboard[user_id] = target
                    app.chat_dashboard[chat_id] = target
                    return int(target)
                try:
                    await app.bot.delete_message(chat_id, target)
                except Exception:
                    pass

        if photo:
            sent = await app.bot.send_photo(
                chat_id,
                photo=photo,
                caption=caption,
                reply_markup=markup,
                parse_mode=app.ParseMode.HTML,
            )
        else:
            sent = await app.bot.send_message(
                chat_id,
                caption,
                reply_markup=markup,
                parse_mode=app.ParseMode.HTML,
            )
        app.user_dashboard[user_id] = sent.message_id
        app.chat_dashboard[chat_id] = sent.message_id
        return int(sent.message_id)

    app._build_and_send_dashboard = build_and_send_graph_dashboard
    app._operator_graph_dashboard_installed = True
