from __future__ import annotations

import asyncio
import html
import os
from typing import Any, Mapping, Optional

import operator_hmi as hmi
import production_bot_ui
from application.operator_snapshot_provider import OperatorSnapshotProvider
from presentation.dark_panel import render_dark_dashboard, render_dark_panel
from runtime.ui.components.operator_graph_policy import (
    _charge_session_active,
    _graph_display_allowed,
    _graph_query_params,
    _hands_off_graph_monitoring,
)
from runtime.ui.components.hmi_action_keyboard import _panel_actions, _toolbar_actions
from runtime.ui.telegram.panel_lifecycle import deliver_graph_edit


_BASE_BUILD_OPERATOR_HMI_STATE = hmi.build_operator_hmi_state
_BASE_RENDER_OPERATOR_PANEL = hmi.render_operator_panel
_BASE_RENDER_OPERATOR_DETAILS = hmi.render_operator_details
_GRAPH_CAPTION = ""


def _dark_panel_enabled() -> bool:
    return os.getenv("OPERATOR_PANEL_STYLE", "text").strip().lower() in {"dark", "dark_card", "image"}


# Compatibility exports; message lifecycle and callbacks remain here.
from runtime.ui.telegram.operator_graph_keyboard import (
    _hide_active_release_button,
    _graph_toolbar,
    _composed_operator_rows,
    _main_graph_markup,
    _active_graph_panel_markup,
)


# Compatibility imports preserve historical call sites while semantic ownership
# remains in operator_hmi. These aliases contain no dashboard policy.
_binary = hmi._binary
_fresh = hmi._fresh
_raw_available = hmi._raw_available
_regulation_fresh = hmi._regulation_fresh
_ownership_conflict = hmi._ownership_conflict
_contain_idle_for_safety = hmi._contain_idle_for_safety


def build_truthful_hmi_state(app: Any, live: Mapping[str, Any], *, base_builder=None) -> hmi.OperatorHmiState:
    return hmi.build_truthful_hmi_state(
        app, live,
        base_builder=base_builder or _BASE_BUILD_OPERATOR_HMI_STATE,
    )


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

    base_panel_renderer = hmi.render_operator_panel

    def truthful_panel(state: hmi.OperatorHmiState) -> str:
        return render_truthful_panel(state, base_renderer=base_panel_renderer)

    def adopt_graph(chat_id: int, user_id: int, message_id: int) -> None:
        # The lifecycle owner is installed after the graph renderer. Resolve
        # it at publication time, not at composition time.
        owner = getattr(app, "terminal_panel_manager", None)
        if owner is not None:
            owner.adopt_graph(chat_id, user_id, message_id)
            return
        # Renderer-only unit tests and pre-install /start fallback.
        app.user_graph_dashboard[user_id] = message_id
        app.chat_graph_dashboard[chat_id] = message_id
        app.user_dashboard[user_id] = message_id
        app.chat_dashboard[chat_id] = message_id

    def forget_graph(chat_id: int, user_id: int, message_id: int) -> None:
        owner = getattr(app, "terminal_panel_manager", None)
        if owner is not None:
            owner.forget_graph(chat_id, user_id, message_id)
            return
        if app.user_graph_dashboard.get(user_id) == message_id:
            app.user_graph_dashboard.pop(user_id, None)
        if app.chat_graph_dashboard.get(chat_id) == message_id:
            app.chat_graph_dashboard.pop(chat_id, None)

    async def retire_graph_workspace_message(app_arg: Any, call: Any) -> None:
        """Best-effort retire a workspace message before sending its replacement."""
        owner = getattr(app_arg, "terminal_panel_manager", None)
        retire = getattr(owner, "retire_graph_workspace_message", None)
        if callable(retire):
            await retire(call)
            return
        try:
            await app_arg.bot.delete_message(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
            )
        except Exception:
            pass

    async def retire_graph_workspace_for_user(chat_id: int, user_id: int) -> None:
        owner = getattr(app, "terminal_panel_manager", None)
        retire = getattr(owner, "retire_graph_workspace_for_user", None)
        if callable(retire):
            await retire(chat_id, user_id)
            return
        message_id = app.user_graph_dashboard.get(user_id)
        if message_id is None:
            return
        forget_graph(chat_id, user_id, message_id)
        try:
            await app.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    async def active_panel_content(user_id: int):
        interface = getattr(app, "operator_interface", None)
        if interface is None:
            return None
        snapshot = await interface.get_operator_snapshot()
        actions = await interface.get_operator_actions(snapshot=snapshot)
        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        actions = _panel_actions(actions, dark=_dark_panel_enabled())
        caption = truthful_panel(state)
        panel_actions = _toolbar_actions(actions)
        markup = _active_graph_panel_markup(app, state, user_id, panel_actions)
        return caption, markup

    async def render_graph_workspace(app_arg: Any, call: Any, user_id: int) -> None:
        """Keep graph range changes to one logical workspace message."""
        if not _graph_display_allowed(app_arg):
            return
        _chart_mode, graph_since, limit_pts = _graph_query_params(app_arg, user_id)
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
        panel_content = await active_panel_content(user_id)
        markup = panel_content[1] if panel_content is not None else hmi._graph_keyboard(app_arg, user_id)
        caption = panel_content[0] if panel_content is not None else _GRAPH_CAPTION
        if getattr(app_arg, "terminal_panel_manager", None) is None:
            adopt_graph(call.message.chat.id, user_id, call.message.message_id)
        if not buf:
            text = "Недостаточно данных."
            photo_source = bool(getattr(call.message, "photo", None))

            async def edit_empty_workspace() -> None:
                await app_arg.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=text,
                    parse_mode=app_arg.ParseMode.HTML,
                    reply_markup=markup,
                )

            async def send_empty_workspace():
                return await call.message.answer(
                    text,
                    parse_mode=app_arg.ParseMode.HTML,
                    reply_markup=markup,
                )

            def retire_empty_graph() -> None:
                forget_graph(call.message.chat.id, user_id, call.message.message_id)

            def adopt_empty_replacement(sent: Any) -> None:
                app_arg.user_dashboard[user_id] = sent.message_id
                app_arg.chat_dashboard[call.message.chat.id] = sent.message_id
                retire_empty_graph()

            owner = getattr(app_arg, "terminal_panel_manager", None)
            if owner is not None:
                await owner.replace_graph_workspace(
                    call,
                    user_id,
                    None if photo_source else edit_empty_workspace,
                    send_empty_workspace,
                    retire_empty_graph,
                    adopt_empty_replacement,
                )
                return

            if not photo_source:
                try:
                    await edit_empty_workspace()
                except Exception as exc:
                    if "message is not modified" in str(exc).lower():
                        retire_empty_graph()
                        return
                else:
                    retire_empty_graph()
                    return
            await retire_graph_workspace_message(app_arg, call)
            sent = await send_empty_workspace()
            adopt_empty_replacement(sent)
            return

        photo = app_arg.BufferedInputFile(buf.getvalue(), filename="rd6018-graph.png")
        media = app_arg.InputMediaPhoto(
            media=photo,
            caption=caption,
            parse_mode=app_arg.ParseMode.HTML,
        )
        async def edit_graph_workspace() -> None:
            await app_arg.bot.edit_message_media(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                media=media,
                reply_markup=markup,
            )

        async def send_graph_replacement():
            return await call.message.answer_photo(
                photo,
                caption=caption,
                parse_mode=app_arg.ParseMode.HTML,
                reply_markup=markup,
            )

        def adopt_replacement_graph(sent: Any) -> None:
            adopt_graph(call.message.chat.id, user_id, sent.message_id)

        owner = getattr(app_arg, "terminal_panel_manager", None)
        if owner is not None:
            await owner.replace_graph_workspace(
                call,
                user_id,
                edit_graph_workspace,
                send_graph_replacement,
                lambda: None,
                adopt_replacement_graph,
            )
            return
        try:
            await edit_graph_workspace()
        except Exception as exc:
            if "message is not modified" in str(exc).lower():
                return
            await retire_graph_workspace_message(app_arg, call)
            sent = await send_graph_replacement()
            adopt_replacement_graph(sent)

    # Keep final presentation and graph transport on this app. HMI composition
    # resolves these callbacks from the app at render time; another composition
    # in this process cannot inherit this app's closures.
    app._render_operator_panel = truthful_panel
    app._render_graph_workspace = render_graph_workspace

    async def publish_graph_workspace(
        chat_id: int,
        user_id: int,
        caption: str,
        reply_markup: Any,
    ) -> Optional[int]:
        """Publish one photo message containing both graph and charge panel."""
        if not _graph_display_allowed(app):
            return None
        _chart_mode, graph_since, limit_pts = _graph_query_params(app, user_id)
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
            return None
        photo = app.BufferedInputFile(buf.getvalue(), filename="rd6018-graph.png")
        cache_key = (
            _chart_mode,
            times[-1] if times else None,
            len(times),
        )

        async def send_graph_workspace():
            return await app.bot.send_photo(
                chat_id,
                photo=photo,
                caption=caption,
                parse_mode=app.ParseMode.HTML,
                reply_markup=reply_markup,
            )

        def remember_graph_samples() -> None:
            app._graph_cache_keys[user_id] = cache_key

        owner = getattr(app, "terminal_panel_manager", None)
        if owner is not None:
            return await owner.publish_graph_workspace(
                chat_id,
                user_id,
                send_graph_workspace,
                remember_graph_samples,
                refresh_graph_message,
            )
        sent = await send_graph_workspace()
        adopt_graph(chat_id, user_id, sent.message_id)
        remember_graph_samples()
        return int(sent.message_id)

    async def refresh_graph_message(chat_id: int, user_id: int, *, force: bool = False) -> None:
        """Refresh only the graph message when the recorder has a new point."""
        graph_message_id = app.user_graph_dashboard.get(user_id)
        if not graph_message_id:
            return
        if not _graph_display_allowed(app):
            await retire_graph_workspace_for_user(chat_id, user_id)
            return
        _chart_mode, graph_since, limit_pts = _graph_query_params(app, user_id)
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
            # The graph has no new recorded point, but the live charge state,
            # countdown and button permissions can still change. Refresh the
            # caption in-place every 60-second tick; never send a new panel.
            panel_content = await active_panel_content(user_id)
            markup = panel_content[1] if panel_content is not None else hmi._graph_keyboard(app, user_id)
            caption = panel_content[0] if panel_content is not None else _GRAPH_CAPTION
            await deliver_graph_edit(
                app, chat_id, user_id, graph_message_id,
                caption=caption, reply_markup=markup,
            )
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
        panel_content = await active_panel_content(user_id)
        markup = panel_content[1] if panel_content is not None else hmi._graph_keyboard(app, user_id)
        caption = panel_content[0] if panel_content is not None else _GRAPH_CAPTION
        edited = await deliver_graph_edit(
            app, chat_id, user_id, graph_message_id,
            caption=caption,
            reply_markup=markup,
            media=app.InputMediaPhoto(
                media=photo,
                caption=caption,
                parse_mode=app.ParseMode.HTML,
            ),
        )
        if not edited:
            return
        app._graph_cache_keys[user_id] = cache_key

    app._refresh_graph_message = refresh_graph_message
    app._retire_graph_workspace_for_user = retire_graph_workspace_for_user

    async def refresh_operator_panel(chat_id: int, user_id: int, message_id: int) -> Optional[int]:
        """Replace the one live panel message without rebuilding the graph."""
        try:
            interface = getattr(app, "operator_interface", None)
            if interface is None:
                raise RuntimeError("operator interface is not installed")
            snapshot = await interface.get_operator_snapshot()
            actions = await interface.get_operator_actions(snapshot=snapshot)
        except Exception as exc:
            app.logger.error("Failed to refresh V3 operator snapshot: %s", exc)
            return None

        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        actions = _panel_actions(actions, dark=_dark_panel_enabled())
        caption = truthful_panel(state)
        panel_actions = _toolbar_actions(actions)
        # A successful start can leave the callback's preview/text message as
        # the tracked dashboard while the graph workspace has not been created
        # yet.  Promote that same message to the single graph+panel workspace;
        # do not leave a second text panel behind.
        if _graph_display_allowed(app) and not app.user_graph_dashboard.get(user_id):
            builder = getattr(app, "_build_and_send_dashboard", None)
            if callable(builder):
                return await builder(
                    chat_id=chat_id,
                    user_id=user_id,
                    old_msg_id=message_id,
                    anchor_msg_id=None,
                )
        markup = (
            app.InlineKeyboardMarkup(
                inline_keyboard=list(
                    hmi.build_operator_keyboard(app, state, actions=panel_actions).inline_keyboard
                )
            )
            if _dark_panel_enabled()
            else _main_graph_markup(app, state, user_id, actions)
        )
        is_graph_message = app.user_graph_dashboard.get(user_id) == message_id
        if is_graph_message and _graph_display_allowed(app):
            markup = _active_graph_panel_markup(app, state, user_id, panel_actions)
            # Back/navigation updates only the graph caption and controls. Rebuilding
            # history here made returning from the journal wait on database/chart work.
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
                await retire_graph_workspace_for_user(chat_id, user_id)
                try:
                    await app.bot.delete_message(chat_id, message_id)
                except Exception:
                    pass
                builder = getattr(app, "_build_and_send_dashboard", None)
                if callable(builder):
                    return await builder(
                        chat_id=chat_id,
                        user_id=user_id,
                        old_msg_id=None,
                        anchor_msg_id=None,
                    )
                return None
        elif is_graph_message:
            await retire_graph_workspace_for_user(chat_id, user_id)
            sent = await app.bot.send_message(
                chat_id,
                caption,
                reply_markup=markup,
                parse_mode=app.ParseMode.HTML,
            )
            app.user_dashboard[user_id] = sent.message_id
            app.chat_dashboard[chat_id] = sent.message_id
            return int(sent.message_id)

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
            actions = await interface.get_operator_actions(snapshot=snapshot)
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
        graph_allowed = _graph_display_allowed(app)
        target = old_msg_id or anchor_msg_id
        tracked_panel = app.user_dashboard.get(user_id) or app.chat_dashboard.get(chat_id)
        if target is None:
            target = tracked_panel
        graph_message_id = app.user_graph_dashboard.get(user_id)
        if graph_allowed and graph_message_id:
            # The graph photo is the authoritative active-charge workspace.
            # A legacy/ delayed refresh may still point user_dashboard at an
            # older text panel; retire that message and refresh the photo only.
            if target is not None and target != graph_message_id:
                try:
                    await app.bot.delete_message(chat_id, target)
                except Exception:
                    pass
            refreshed = await refresh_operator_panel(
                chat_id,
                user_id,
                int(graph_message_id),
            )
            if refreshed is not None:
                return int(refreshed)
            app.user_dashboard[user_id] = graph_message_id
            app.chat_dashboard[chat_id] = graph_message_id
            return int(graph_message_id)
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
                graph_markup = _active_graph_panel_markup(app, state, user_id, panel_actions)
                graph_message_id = await publish_graph_workspace(
                    chat_id,
                    user_id,
                    caption,
                    graph_markup,
                )
                if graph_message_id is not None:
                    return graph_message_id
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

    async def restore_dashboard_to_bottom(chat_id: int, user_id: int) -> int:
        """Recreate the dashboard after a secondary screen so it is last in chat.

        Telegram cannot reorder an existing message. Retire the tracked dashboard
        and graph together, then let the same production renderer recreate the
        current photo chart/control panel (or its text fallback) after the journal.
        """
        async def rebuild() -> int:
            ids = {
                value for value in (
                    app.user_dashboard.get(user_id),
                    app.chat_dashboard.get(chat_id),
                    app.user_graph_dashboard.get(user_id),
                    app.chat_graph_dashboard.get(chat_id),
                ) if value is not None
            }
            for mapping, key in (
                (app.user_dashboard, user_id),
                (app.chat_dashboard, chat_id),
                (app.user_graph_dashboard, user_id),
                (app.chat_graph_dashboard, chat_id),
            ):
                mapping.pop(key, None)
            app._graph_cache_keys.pop(user_id, None)
            for message_id in ids:
                try:
                    await app.bot.delete_message(chat_id, int(message_id))
                except Exception:
                    # A deleted/stale Telegram message is already retired for ordering.
                    pass
            return await build_and_send_graph_dashboard(
                chat_id=chat_id,
                user_id=user_id,
                old_msg_id=None,
                anchor_msg_id=None,
            )

        return await rebuild()

    app._build_and_send_dashboard = build_and_send_graph_dashboard
    app._restore_dashboard_to_bottom = restore_dashboard_to_bottom
    app._operator_graph_dashboard_installed = True
