from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional

import operator_hmi as hmi
from rd6018_telemetry import (
    ProtectionStatus,
    RegulationMode,
    resolve_protection,
    resolve_regulation,
    telemetry_freshness,
)


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


def _fresh(live: Mapping[str, Any], *keys: str) -> bool:
    return bool(telemetry_freshness(live, keys).valid)


def _raw_available(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() not in _UNKNOWN


def _protection_fresh(live: Mapping[str, Any]) -> bool:
    if _raw_available(live.get("protection_code")):
        return _fresh(live, "protection_code")
    return _fresh(live, "ovp_triggered", "ocp_triggered")


def _regulation_fresh(live: Mapping[str, Any]) -> bool:
    if _raw_available(live.get("regulation_code")):
        return _fresh(live, "regulation_code")
    return _fresh(live, "is_cv", "is_cc")


def _ownership_conflict(app: Any) -> Optional[str]:
    """Return a presentation-level ownership conflict without changing authority.

    The operator panel must never silently choose one owner when runtime objects claim
    incompatible control domains. A live observer is intentionally paired with
    HANDS_OFF; that pair is valid. Managed AUTO/Manual ownership is not.
    """
    controller = getattr(app, "charge_controller", None)
    auto_active = bool(controller is not None and getattr(controller, "is_active", False))

    manual = getattr(app, "manual_session_manager", None)
    manual_active = bool(manual is not None and getattr(manual, "is_active", False))

    manager = getattr(app, "rd_control_mode_manager", None)
    hands_off = bool(manager is not None and getattr(manager, "hands_off", False))

    observer = getattr(app, "rd_live_mix_observer", None)
    observer_state = ""
    if observer is not None:
        raw_state = getattr(observer, "state", None)
        observer_state = str(getattr(raw_state, "value", raw_state) or "")
    observer_visible = observer is not None and observer_state in {
        "active",
        "off_pending",
        "interrupted",
    }

    conflicts: list[str] = []
    if auto_active and manual_active:
        conflicts.append("AUTO и MANUAL активны одновременно")
    if observer_visible and (auto_active or manual_active):
        managed = "AUTO" if auto_active and not manual_active else "MANUAL" if manual_active and not auto_active else "AUTO/MANUAL"
        conflicts.append(f"{managed} конфликтует с подхваченным Mix")
    if observer_visible and not hands_off:
        conflicts.append("подхваченный Mix существует вне HANDS_OFF")
    if hands_off and (auto_active or manual_active):
        managed = "AUTO" if auto_active and not manual_active else "MANUAL" if manual_active and not auto_active else "AUTO/MANUAL"
        conflicts.append(f"{managed} активен при HANDS_OFF")

    return "; ".join(conflicts) if conflicts else None


def _contain_idle_for_safety(
    state: hmi.OperatorHmiState,
    *,
    title: str,
    progress: str,
    safety: str,
    attention: str,
) -> hmi.OperatorHmiState:
    """Idle may expose Start only when safety state is positively usable."""
    if state.process_state is not hmi.HmiProcessState.IDLE:
        return replace(state, safety=safety, attention=attention)
    return replace(
        state,
        process_state=hmi.HmiProcessState.CONTAINMENT,
        authority=hmi.HmiAuthority.CONTAINMENT,
        title=title,
        progress=progress,
        safety=safety,
        attention=attention,
    )


def build_truthful_hmi_state(
    app: Any,
    live: Mapping[str, Any],
    *,
    base_builder=None,
) -> hmi.OperatorHmiState:
    """Fail truthful at the presentation boundary without inventing actuator state.

    Runtime safety already fails closed on missing/stale/unknown critical telemetry.
    The HMI mirrors that truth: stale/unknown Output is not OFF, idle Start is not
    offered without a usable protection state, raw regulation/protection codes take
    precedence over legacy compatibility sensors, and contradictory owner claims are
    surfaced as containment instead of being resolved by display precedence.
    """
    builder = base_builder or _BASE_BUILD_OPERATOR_HMI_STATE
    state = builder(app, live)

    output_state = _binary(live.get("switch"))
    output_fresh = _fresh(live, "switch")
    if output_state is None or not output_fresh:
        reason = (
            "Физическое состояние Output неизвестно"
            if output_state is None
            else "Телеметрия Output устарела"
        )
        return replace(
            state,
            process_state=hmi.HmiProcessState.CONTAINMENT,
            authority=hmi.HmiAuthority.CONTAINMENT,
            title="RD6018 · OUTPUT НЕ ПОДТВЕРЖДЁН",
            output_on=False,
            regulator="—",
            progress=f"{reason} · новые команды запуска недоступны",
            safety="⚠️ Требуется восстановить достоверную телеметрию RD6018",
            attention="output_unknown",
        )

    # Display the same canonical regulation decoder used by the safety layer. An
    # unknown or stale mode is shown as unknown rather than trusting legacy flags.
    regulation = resolve_regulation(live)
    if _regulation_fresh(live):
        regulator = {
            RegulationMode.CV: "CV",
            RegulationMode.CC: "CC",
        }.get(regulation, "—")
    else:
        regulator = "—"
    if regulator != state.regulator:
        state = replace(state, regulator=regulator)

    ownership_conflict = _ownership_conflict(app)
    if ownership_conflict:
        state = replace(
            state,
            process_state=hmi.HmiProcessState.CONTAINMENT,
            authority=hmi.HmiAuthority.CONTAINMENT,
            title="RD6018 · КОНФЛИКТ OWNERSHIP",
            output_on=bool(output_state),
            progress=f"Несогласованная модель управления: {ownership_conflict}",
            safety="⚠️ Управляющие действия скрыты до восстановления единственного owner",
            attention="alarm",
        )

    protection = resolve_protection(live)
    if not _protection_fresh(live) or protection.status is ProtectionStatus.UNKNOWN:
        return _contain_idle_for_safety(
            state,
            title="RD6018 · ЗАЩИТА НЕ ПОДТВЕРЖДЕНА",
            progress="Новая программа недоступна до достоверного статуса защит RD6018",
            safety="⚠️ Статус защит RD6018 не подтверждён",
            attention="alarm" if output_state else "warning",
        )

    if protection.tripped:
        label = {
            ProtectionStatus.OVP: "OVP",
            ProtectionStatus.OCP: "OCP",
            ProtectionStatus.OPP: "OPP",
        }.get(protection.status, protection.status.value.upper())
        return _contain_idle_for_safety(
            state,
            title=f"RD6018 · СРАБОТАЛА ЗАЩИТА {label}",
            progress="Новая программа недоступна до проверки и сброса защитного состояния",
            safety=f"⚠️ Защита: {label}",
            attention="alarm",
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

    async def retire_graph_workspace_message(app_arg: Any, call: Any) -> None:
        """Best-effort retire a workspace message before sending its replacement."""
        try:
            await app_arg.bot.delete_message(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
            )
        except Exception:
            pass

    async def render_graph_workspace(app_arg: Any, call: Any, user_id: int) -> None:
        """Keep graph range changes to one logical workspace message."""
        _chart_mode, graph_since, limit_pts = app_arg._chart_query_params(user_id)
        times, voltages, currents, temps = await app_arg.get_graph_data_with_temp(
            limit=limit_pts,
            since_timestamp=graph_since,
        )
        buf = await app_arg.asyncio.to_thread(
            app_arg.generate_chart,
            times,
            voltages,
            currents,
            temps,
        )
        markup = hmi._graph_keyboard(app_arg, user_id)
        if not buf:
            text = "<b>График RD6018</b>\n\nНедостаточно данных."
            try:
                await app_arg.bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption=text,
                    parse_mode=app_arg.ParseMode.HTML,
                    reply_markup=markup,
                )
            except Exception as exc:
                if "message is not modified" in str(exc).lower():
                    return
                await retire_graph_workspace_message(app_arg, call)
                await call.message.answer(
                    text,
                    parse_mode=app_arg.ParseMode.HTML,
                    reply_markup=markup,
                )
            return

        photo = app_arg.BufferedInputFile(buf.getvalue(), filename="rd6018-graph.png")
        media = app_arg.InputMediaPhoto(
            media=photo,
            caption="<b>График RD6018</b>",
            parse_mode=app_arg.ParseMode.HTML,
        )
        try:
            await app_arg.bot.edit_message_media(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                media=media,
                reply_markup=markup,
            )
        except Exception as exc:
            if "message is not modified" in str(exc).lower():
                return
            await retire_graph_workspace_message(app_arg, call)
            await call.message.answer_photo(
                photo,
                caption="<b>График RD6018</b>",
                parse_mode=app_arg.ParseMode.HTML,
                reply_markup=markup,
            )

    # operator_hmi handlers resolve these globals at call time, so details, graph
    # workspace and compact caption inherit the final production presentation rules.
    hmi.build_operator_hmi_state = truthful_builder
    hmi.render_operator_panel = truthful_panel
    hmi.render_operator_details = truthful_details
    hmi._render_graph_workspace = render_graph_workspace

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
