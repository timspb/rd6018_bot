from __future__ import annotations

import asyncio
import html
import os
from dataclasses import replace
from typing import Any, Mapping, Optional

import operator_hmi as hmi
import v2_bot_ui
from application.operator_snapshot_provider import OperatorSnapshotProvider
from presentation.dark_panel import render_dark_dashboard, render_dark_panel
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
GRAPH_REFRESH_SEC = 60.0
_GRAPH_CAPTION = ""


def _dark_panel_enabled() -> bool:
    return os.getenv("OPERATOR_PANEL_STYLE", "text").strip().lower() in {"dark", "dark_card", "image"}


def _charge_session_active(app: Any) -> bool:
    controller = getattr(app, "charge_controller", None)
    if controller is not None and bool(getattr(controller, "is_active", False)):
        return True
    manual = getattr(app, "manual_session_manager", None)
    if manual is not None and bool(getattr(manual, "is_active", False)):
        return True
    observer = getattr(app, "rd_live_mix_observer", None)
    return observer is not None and str(getattr(observer, "state", "")) in {"active", "off_pending"}


def _panel_actions(actions, *, dark: bool):
    """Apply presentation-only visibility rules to the immutable action view."""
    if actions is None or not dark:
        return actions
    hidden = {hmi.OperatorAction.SHOW_DIAGNOSTICS}
    return replace(
        actions,
        available_actions=tuple(item for item in actions.available_actions if item.action not in hidden),
    )


def _toolbar_actions(actions):
    """Keep graph ranges and the log in the dedicated top toolbar only."""
    if actions is None:
        return None
    hidden = {hmi.OperatorAction.SHOW_LOG, hmi.OperatorAction.SHOW_GRAPH}
    return replace(
        actions,
        available_actions=tuple(item for item in actions.available_actions if item.action not in hidden),
    )


def _graph_toolbar(app: Any, user_id: int, actions=None):
    graph_rows = hmi._graph_keyboard(app, user_id).inline_keyboard
    top_row = list(graph_rows[0]) if graph_rows else []
    if actions is not None and any(
        item.action is hmi.OperatorAction.SHOW_LOG for item in actions.available_actions
    ):
        top_row.append(app.InlineKeyboardButton(text="📋 Лог", callback_data="logs"))
    return top_row


def _main_graph_markup(app: Any, state: hmi.OperatorHmiState, user_id: int, actions=None):
    """Render the charge panel without graph controls or graph work."""
    # Older composition wrappers preserve the two-argument builder signature.
    # The V3 path passes capabilities explicitly; compatibility callers retain
    # the unchanged legacy fallback.
    # The root dashboard uses the existing state-driven RD control screen.  The
    # capability view remains available to callers, but must not replace the
    # ownership/autonomous composition on the root screen.
    panel = hmi.build_operator_keyboard(app, state)
    return app.InlineKeyboardMarkup(
        inline_keyboard=list(panel.inline_keyboard)
    )


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

    app.user_graph_dashboard = getattr(app, "user_graph_dashboard", {})
    app.chat_graph_dashboard = getattr(app, "chat_graph_dashboard", {})
    app._graph_cache_keys = getattr(app, "_graph_cache_keys", {})
    app._graph_update_lock = getattr(app, "_graph_update_lock", asyncio.Lock())

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

    async def retire_graph_workspace_for_user(chat_id: int, user_id: int) -> None:
        message_id = app.user_graph_dashboard.pop(user_id, None)
        if message_id is None:
            return
        if app.chat_graph_dashboard.get(chat_id) == message_id:
            app.chat_graph_dashboard.pop(chat_id, None)
        try:
            await app.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    async def render_graph_workspace(app_arg: Any, call: Any, user_id: int) -> None:
        """Keep graph range changes to one logical workspace message."""
        if not _charge_session_active(app_arg):
            return
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
        app_arg.user_graph_dashboard[user_id] = call.message.message_id
        app_arg.chat_graph_dashboard[call.message.chat.id] = call.message.message_id
        if not buf:
            text = "Недостаточно данных."
            # A photo message cannot truthfully become an empty text workspace by
            # editing only its caption: the old graph would remain visible. Replace
            # the workspace instead of leaving stale plotted data on screen.
            if bool(getattr(call.message, "photo", None)):
                await retire_graph_workspace_message(app_arg, call)
                await call.message.answer(
                    text,
                    parse_mode=app_arg.ParseMode.HTML,
                    reply_markup=markup,
                )
                return
            try:
                await app_arg.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=text,
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
            caption=_GRAPH_CAPTION,
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
                caption=_GRAPH_CAPTION,
                parse_mode=app_arg.ParseMode.HTML,
                reply_markup=markup,
            )

    # operator_hmi handlers resolve these globals at call time, so details, graph
    # workspace and compact caption inherit the final production presentation rules.
    hmi.build_operator_hmi_state = truthful_builder
    hmi.render_operator_panel = truthful_panel
    hmi.render_operator_details = truthful_details
    hmi._render_graph_workspace = render_graph_workspace

    async def publish_graph_workspace(chat_id: int, user_id: int) -> None:
        """Publish the initial graph before the text charge workspace."""
        if not _charge_session_active(app):
            return
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
        if not buf:
            return
        photo = app.BufferedInputFile(buf.getvalue(), filename="rd6018-graph.png")
        sent = await app.bot.send_photo(
            chat_id,
            photo=photo,
            caption=_GRAPH_CAPTION,
            parse_mode=app.ParseMode.HTML,
            reply_markup=hmi._graph_keyboard(app, user_id),
        )
        app.user_graph_dashboard[user_id] = sent.message_id
        app.chat_graph_dashboard[chat_id] = sent.message_id
        app._graph_cache_keys[user_id] = (
            _chart_mode,
            times[-1] if times else None,
            len(times),
        )
        ensure_graph_refresh_loop()

    async def refresh_graph_message(chat_id: int, user_id: int, *, force: bool = False) -> None:
        """Refresh only the graph message when the recorder has a new point."""
        graph_message_id = app.user_graph_dashboard.get(user_id)
        if not graph_message_id:
            return
        if not _charge_session_active(app):
            await retire_graph_workspace_for_user(chat_id, user_id)
            return
        async with app._graph_update_lock:
            _chart_mode, graph_since, limit_pts = app._chart_query_params(user_id)
            times, voltages, currents, temps = await app.get_graph_data_with_temp(
                limit=limit_pts,
                since_timestamp=graph_since,
            )
            cache_key = (
                _chart_mode,
                times[-1] if times else None,
                len(times),
            )
            if not force and app._graph_cache_keys.get(user_id) == cache_key:
                return
            buf = await app.asyncio.to_thread(
                app.generate_chart,
                times,
                voltages,
                currents,
                temps,
            )
            if not buf:
                return
            photo = app.BufferedInputFile(buf.getvalue(), filename="rd6018-graph.png")
            markup = hmi._graph_keyboard(app, user_id)
            try:
                await app.bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=graph_message_id,
                    media=app.InputMediaPhoto(
                        media=photo,
                        caption=_GRAPH_CAPTION,
                        parse_mode=app.ParseMode.HTML,
                    ),
                    reply_markup=markup,
                )
            except Exception as exc:
                if "message is not modified" not in str(exc).lower():
                    app.logger.debug("graph refresh failed: %s", exc)
                    return
            app._graph_cache_keys[user_id] = cache_key

    async def graph_refresh_loop() -> None:
        while True:
            await asyncio.sleep(GRAPH_REFRESH_SEC)
            for user_id, message_id in list(app.user_graph_dashboard.items()):
                chat_id = next(
                    (chat for chat, current in app.chat_graph_dashboard.items() if current == message_id),
                    None,
                )
                if chat_id is None:
                    continue
                try:
                    await refresh_graph_message(chat_id, user_id)
                except Exception as exc:
                    app.logger.debug("periodic graph refresh failed: %s", exc)

    def ensure_graph_refresh_loop() -> None:
        task = getattr(app, "_graph_refresh_task", None)
        if task is None or task.done():
            app._graph_refresh_task = asyncio.create_task(graph_refresh_loop())

    app._refresh_graph_message = refresh_graph_message
    app._ensure_graph_refresh_loop = ensure_graph_refresh_loop

    async def refresh_operator_panel(chat_id: int, user_id: int, message_id: int) -> Optional[int]:
        """Replace the one live panel message without rebuilding the graph."""
        try:
            interface = getattr(app, "operator_interface", None)
            if interface is None:
                raise RuntimeError("operator interface is not installed")
            snapshot = await interface.get_operator_snapshot()
            actions = await interface.get_operator_actions()
        except Exception as exc:
            app.logger.error("Failed to refresh V3 operator snapshot: %s", exc)
            return None

        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        actions = _panel_actions(actions, dark=_dark_panel_enabled())
        caption = truthful_panel(state)
        selected_program = v2_bot_ui.selected_program_for_user(user_id)
        if selected_program:
            caption += (
                "\n\n<b>Выбрана программа:</b> "
                f"{html.escape(selected_program)}"
                "\n<i>V/I ниже — фактический readback RD6018.</i>"
            )
        panel_actions = _toolbar_actions(actions)
        markup = (
            app.InlineKeyboardMarkup(
                inline_keyboard=list(
                    hmi.build_operator_keyboard(app, state, actions=panel_actions).inline_keyboard
                )
            )
            if _dark_panel_enabled()
            else _main_graph_markup(app, state, user_id, actions)
        )

        if _dark_panel_enabled():
            card = app.BufferedInputFile(render_dark_panel(caption), filename="rd6018-panel.png")
            try:
                await app.bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=app.InputMediaPhoto(media=card, caption=""),
                    reply_markup=markup,
                )
                return int(message_id)
            except Exception as exc:
                if "message is not modified" in str(exc).lower():
                    return int(message_id)
                try:
                    await app.bot.delete_message(chat_id, message_id)
                except Exception:
                    pass
                sent = await app.bot.send_photo(chat_id, photo=card, caption="", reply_markup=markup)
                app.user_dashboard[user_id] = sent.message_id
                app.chat_dashboard[chat_id] = sent.message_id
                return int(sent.message_id)

        try:
            await app.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                reply_markup=markup,
                parse_mode=app.ParseMode.HTML,
            )
            return int(message_id)
        except Exception as exc:
            if "message is not modified" in str(exc).lower():
                return int(message_id)

        # A text dashboard can still exist from an older runtime; update it without
        # falling back to the expensive chart-producing path.
        try:
            await app.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=caption,
                reply_markup=markup,
                parse_mode=app.ParseMode.HTML,
            )
            return int(message_id)
        except Exception as text_exc:
            app.logger.warning("operator panel refresh failed: %s", text_exc)
            try:
                await app.bot.delete_message(chat_id, message_id)
            except Exception:
                pass
            sent = await app.bot.send_message(
                chat_id,
                caption,
                reply_markup=markup,
                parse_mode=app.ParseMode.HTML,
            )
            app.user_dashboard[user_id] = sent.message_id
            app.chat_dashboard[chat_id] = sent.message_id
            return int(sent.message_id)

    app._refresh_operator_panel = refresh_operator_panel

    async def build_and_send_graph_dashboard(
        chat_id: int,
        user_id: int,
        old_msg_id: Optional[int] = None,
        anchor_msg_id: Optional[int] = None,
    ) -> int:
        """Publish the ordinary dashboard without entering the charting stack.

        Graph rendering is intentionally limited to ``render_graph_workspace`` above,
        which is reached only by an explicit operator graph request.  The terminal
        panel middleware calls this builder for routine Telegram events, so keeping
        this path text-only prevents repeated native Matplotlib/NumPy allocations.
        """
        actions = None
        try:
            interface = getattr(app, "operator_interface", None)
            if interface is None:
                raise RuntimeError("operator interface is not installed")
            snapshot = await interface.get_operator_snapshot()
            actions = await interface.get_operator_actions()
        except Exception as exc:
            app.logger.error("Failed to get V3 operator snapshot for dashboard: %s", exc)
            snapshot = None

        state = (
            OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
            if snapshot is not None
            else hmi.OperatorHmiState(
                hmi.HmiProcessState.CONTAINMENT,
                hmi.HmiAuthority.CONTAINMENT,
                "RD6018 · Состояние неизвестно",
                False,
                "—",
                "",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "Телеметрия недоступна",
                "⚠️ Состояние не подтверждено",
                attention="output_unknown",
            )
        )
        caption = truthful_panel(state)
        actions = _panel_actions(actions, dark=_dark_panel_enabled())
        panel_actions = _toolbar_actions(actions)
        markup = (
            app.InlineKeyboardMarkup(
            inline_keyboard=list(hmi.build_operator_keyboard(app, state, actions=panel_actions).inline_keyboard)
            )
            if _dark_panel_enabled()
            else _main_graph_markup(app, state, user_id, actions)
        )

        # Only the first dashboard path without a graph workspace publishes the
        # graph. Callback-driven charge-panel refreshes never enter the charting
        # stack. If a restart left an old charge message tracked but no graph
        # workspace, retire that
        # message first so the new graph is immediately followed by the new
        # charge panel in Telegram's append-only message order.
        target = old_msg_id or anchor_msg_id
        graph_allowed = _charge_session_active(app)
        if not graph_allowed:
            await retire_graph_workspace_for_user(chat_id, user_id)
        initial_graph = graph_allowed and not app.user_graph_dashboard.get(user_id)
        if initial_graph and target:
            try:
                await app.bot.delete_message(chat_id, target)
            except Exception:
                pass
            target = None
        if initial_graph:
            try:
                await publish_graph_workspace(chat_id, user_id)
            except Exception as exc:
                app.logger.debug("initial graph workspace publish failed: %s", exc)

        if target:
            try:
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
