from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from enum import Enum
from typing import Any, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA
from runtime.ui.telegram.off_conditions import OFF_CALLBACK_DATA

from runtime.safety.runtime_guard import RuntimeSafetyError, logger
from runtime.safety.managed_guard import ManagedRuntimeSafetyGuard
from rd6018_telemetry import telemetry_freshness


class RdControlMode(str, Enum):
    """Who owns RD6018 actuator authority."""

    PB_MANAGED = "pb_managed"
    HANDS_OFF = "hands_off"


class RdControlModeManager:
    """Durable operator ownership switch above all Pb charging semantics.

    HANDS_OFF means the RD6018 is being used as a general-purpose power supply.
    The bot may observe telemetry, but all bot actuator paths are blocked and the
    Pb runtime-safety guard is bypassed. The only actuator still exposed by this
    manager is an explicit operator-requested, positively verified Output OFF.
    """

    STATE_VERSION = 1

    def __init__(self, app: Any, *, state_file: Optional[str] = None) -> None:
        self.app = app
        self.guard = getattr(app, "runtime_safety_guard", None)
        if not isinstance(self.guard, ManagedRuntimeSafetyGuard):
            raise RuntimeError("RD control mode requires ManagedRuntimeSafetyGuard")
        self.state_file = str(
            state_file
            or getattr(app, "rd_control_mode_file", "rd_control_mode_v2.json")
        )
        self.mode = RdControlMode.PB_MANAGED
        self.persistence_ok = True
        self._transition_lock = asyncio.Lock()
        self._release_in_progress = False
        self._edge_autonomous = False
        self._load()

    @property
    def hands_off(self) -> bool:
        return self.mode is RdControlMode.HANDS_OFF

    @property
    def pb_managed(self) -> bool:
        return self.mode is RdControlMode.PB_MANAGED

    @property
    def release_in_progress(self) -> bool:
        return bool(self._release_in_progress)

    @property
    def edge_autonomous(self) -> bool:
        return bool(self._edge_autonomous)

    def _record_edge_autonomous(self, active: bool) -> None:
        """Update the in-memory mirror of the edge-owned persistent mode."""
        if not isinstance(active, bool):
            raise TypeError("edge autonomous observation must be an explicit bool")
        self._edge_autonomous = active

    def _observe_edge_mode(self, live: Any) -> None:
        if not isinstance(live, dict):
            return
        raw = live.get("autonomous_mode")
        if isinstance(raw, bool):
            self._record_edge_autonomous(raw)
        elif isinstance(raw, (int, float)) and raw in (0, 1):
            self._record_edge_autonomous(bool(raw))
        elif isinstance(raw, str):
            value = raw.strip().lower()
            if value in {"on", "true", "1"}:
                self._record_edge_autonomous(True)
            elif value in {"off", "false", "0"}:
                self._record_edge_autonomous(False)

    def _load(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if int(raw.get("version")) != self.STATE_VERSION:
                raise ValueError("unsupported RD control-mode state version")
            self.mode = RdControlMode(str(raw.get("mode")))
            self.persistence_ok = True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Never infer HANDS_OFF from corrupt state. Existing managed safety remains
            # authoritative until the operator explicitly removes it again.
            self.mode = RdControlMode.PB_MANAGED
            self.persistence_ok = False

    def _write_mode(self, mode: RdControlMode) -> None:
        path = os.path.abspath(self.state_file)
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        document = {
            "version": self.STATE_VERSION,
            "mode": mode.value,
            "updated_at": time.time(),
        }
        fd, tmp_path = tempfile.mkstemp(
            prefix=".rd-control-mode-",
            suffix=".tmp",
            dir=directory,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            try:
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            self.persistence_ok = False
            raise
        self.persistence_ok = True

    def _managed_session_active(self) -> bool:
        controller = getattr(self.app, "charge_controller", None)
        manual = getattr(self.app, "manual_session_manager", None)
        return bool(
            (controller is not None and getattr(controller, "is_active", False))
            or (manual is not None and getattr(manual, "is_active", False))
        )

    def _clear_stale_auto_restore_authority(self) -> None:
        """HANDS_OFF is an ownership boundary; an old AUTO session may not revive later."""
        controller = getattr(self.app, "charge_controller", None)
        if controller is None or getattr(controller, "is_active", False):
            return
        clear = getattr(controller, "_clear_session_file", None)
        if callable(clear):
            clear()

    async def enter_hands_off(self) -> bool:
        async with self._transition_lock:
            if self.hands_off:
                return True
            if bool(getattr(self.guard, "_off_unconfirmed", False)):
                raise RuntimeSafetyError(
                    "RD HANDS_OFF blocked: previous managed Output OFF is still unconfirmed"
                )
            if self._managed_session_active():
                raise RuntimeSafetyError(
                    "RD HANDS_OFF blocked: active managed charge requires explicit release confirmation"
                )

            self._release_in_progress = True
            try:
                if bool(getattr(self.guard, "edge_lease_enforced", False)):
                    lease = getattr(self.guard, "edge_safety_lease", None)
                    if lease is None:
                        raise RuntimeSafetyError(
                            "RD HANDS_OFF blocked: edge safety lease cannot be disarmed"
                        )
                    try:
                        disarmed = bool(await lease.disarm())
                    except Exception as exc:
                        raise RuntimeSafetyError(
                            f"RD HANDS_OFF blocked: edge safety lease disarm failed: {exc}"
                        ) from exc
                    if not disarmed:
                        raise RuntimeSafetyError(
                            "RD HANDS_OFF blocked: edge safety lease disarm was not confirmed"
                        )

                # Commit durability before changing in-process authority.
                self._write_mode(RdControlMode.HANDS_OFF)
                self.mode = RdControlMode.HANDS_OFF
                self.guard._orphan_output_seen_at = None
                self._clear_stale_auto_restore_authority()
                return True
            finally:
                self._release_in_progress = False

    def _fresh_output_off_evidence(self, live: dict[str, Any]) -> bool:
        """Require canonical OFF plus freshness for the source that owns it."""
        evidence = self.guard._output_evidence(live)
        meta = live.get("_meta")
        source_key = str(evidence.source_key or "switch")
        if source_key == "output_state_code_v2":
            source_meta = meta.get(source_key) if isinstance(meta, dict) else None
            switch_meta = meta.get("switch") if isinstance(meta, dict) else None
            if not isinstance(source_meta, dict) and (
                isinstance(switch_meta, dict)
                and switch_meta.get("source_key") == source_key
            ):
                source_key = "switch"
        freshness = telemetry_freshness(live, (source_key,))
        if not freshness.valid:
            return False
        if evidence.requires_fresh_heartbeat and evidence.heartbeat_epoch is None:
            return False
        return evidence.state is False

    async def _require_edge_lease_unarmed(self) -> None:
        if not bool(getattr(self.guard, "edge_lease_enforced", False)):
            return
        lease = getattr(self.guard, "edge_safety_lease", None)
        if lease is None:
            raise RuntimeSafetyError(
                "PB control restore blocked: required edge safety lease is unavailable"
            )

        # HANDS_OFF must not renew an old managed lease while ownership is being
        # returned. Keep renewals suspended on every failure; a fresh START explicitly
        # arms the same lease again after PB authority is durable.
        lease.suspend_renewals()
        try:
            state = await lease.read_state()
        except Exception as exc:
            raise RuntimeSafetyError(
                f"PB control restore blocked: edge safety lease state is unavailable ({exc})"
            ) from exc

        def healthy_unarmed(snapshot: Any) -> bool:
            return bool(
                not snapshot.armed
                and not snapshot.tripped
                and not snapshot.boot_quarantine
                and lease._fresh_modbus(snapshot)
                and snapshot.remaining_s is not None
                and snapshot.remaining_s <= lease.config.ack_remaining_slack_s
            )

        if state.tripped or state.boot_quarantine or not lease._fresh_modbus(state):
            raise RuntimeSafetyError(
                "PB control restore blocked: edge safety lease is tripped, quarantined or stale"
            )
        if (
            state.armed
            or state.remaining_s is None
            or state.remaining_s > lease.config.ack_remaining_slack_s
        ):
            try:
                disarmed = bool(await lease.disarm())
            except Exception as exc:
                raise RuntimeSafetyError(
                    f"PB control restore blocked: edge lease disarm failed ({exc})"
                ) from exc
            if not disarmed:
                raise RuntimeSafetyError(
                    "PB control restore blocked: edge lease disarm was not positively acknowledged"
                )
            try:
                state = await lease.read_state()
            except Exception as exc:
                raise RuntimeSafetyError(
                    f"PB control restore blocked: edge lease post-disarm read is unavailable ({exc})"
                ) from exc
        if not healthy_unarmed(state):
            raise RuntimeSafetyError(
                "PB control restore blocked: edge lease is not positively unarmed and healthy"
            )

    async def return_pb_control(self) -> bool:
        async with self._transition_lock:
            if self.pb_managed:
                return True
            if self._managed_session_active():
                raise RuntimeSafetyError(
                    "PB control restore blocked: stale managed software authority is still active"
                )
            from application.execution_port import get_or_create_execution_port

            # Read through the composed Safety owner. A raw/stale legacy switch
            # value must never override canonical V2 Output state or its heartbeat.
            port = get_or_create_execution_port(self.app)
            live = await port.read_live()
            if not self._fresh_output_off_evidence(dict(live)):
                if bool(getattr(self.guard, "_off_unconfirmed", False)):
                    raise RuntimeSafetyError(
                        "PB control restore blocked: Output OFF remains unconfirmed"
                    )
                raise RuntimeSafetyError(
                    "PB control restore requires fresh confirmed Output OFF; current RD state was not changed"
                )
            await self._require_edge_lease_unarmed()
            # A physical/manual OFF observed through the composed Safety boundary also
            # clears a prior failed explicit HANDS_OFF OFF attempt. Discard any pre-HANDS_OFF AUTO
            # restore file so returning control always requires a fresh operator start.
            self.guard._off_unconfirmed = False
            self._clear_stale_auto_restore_authority()
            self._write_mode(RdControlMode.PB_MANAGED)
            self.mode = RdControlMode.PB_MANAGED
            self.guard._orphan_output_seen_at = None
            return True

    async def operator_output_off(self, entity_id: Optional[str] = None) -> bool:
        """Explicit HANDS_OFF OFF without re-enabling Pb authority."""
        if not self.hands_off:
            raise RuntimeSafetyError(
                "explicit RD-mode Output OFF is available only in HANDS_OFF"
            )

        from application.execution_port import get_or_create_execution_port

        port = get_or_create_execution_port(self.app)
        confirmed = bool(
            await port.request_emergency_off(
                entity_id,
                allow_hands_off_operator_off=True,
            )
        )
        # ExecutionPort delegates to the canonical physical owner, whose verified
        # turn_off transaction already disarms any residual edge lease. Do not issue a
        # second disarm here: HANDS_OFF containment must perform exactly one OFF/disarm.
        return confirmed


def _strip_callbacks(
    markup: InlineKeyboardMarkup,
    blocked: set[str],
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for row in markup.inline_keyboard:
        filtered = [
            button
            for button in row
            if str(getattr(button, "callback_data", "") or "") not in blocked
        ]
        if filtered:
            rows.append(filtered)
    return rows


def install_rd_control_mode(app: Any, *, install_ui: bool = True) -> RdControlModeManager:
    """Install the persistent general-purpose RD6018 ownership mode."""
    existing = getattr(app, "rd_control_mode_manager", None)
    if isinstance(existing, RdControlModeManager):
        return existing

    manager = RdControlModeManager(app)
    app.rd_control_mode_manager = manager
    guard = manager.guard
    # Actuation ownership/policy is centralized in ExecutionPort. HassClient is
    # transport/read-only here and must never be monkeypatched by ownership mode.

    controller = getattr(app, "charge_controller", None)
    # Canonical automatic START admission is owned by ExecutionPort before
    # controller state mutation. Restore has a separate recovery contract below.
    if controller is not None and callable(getattr(controller, "try_restore_session", None)) and not getattr(
        controller, "_rd_control_mode_restore_wrapped", False
    ):
        original_restore = controller.try_restore_session

        def guarded_restore(*args: Any, **kwargs: Any) -> Any:
            if manager.hands_off or manager.edge_autonomous or manager.release_in_progress:
                return False, None
            return original_restore(*args, **kwargs)

        controller.try_restore_session = guarded_restore
        controller._rd_control_mode_restore_wrapped = True

    manual = getattr(app, "manual_session_manager", None)
    if manual is not None and not getattr(
        manual, "_rd_control_mode_start_wrapped", False
    ):
        original_manual_start = manual.start

        async def guarded_manual_start(*args: Any, **kwargs: Any) -> bool:
            if manager.hands_off or manager.edge_autonomous or manager.release_in_progress:
                raise RuntimeSafetyError(
                    "RD AUTONOMOUS: Manual charge start is disabled"
                    if manager.edge_autonomous
                    else "RD HANDS_OFF: Manual charge start is disabled"
                )
            return bool(await original_manual_start(*args, **kwargs))

        manual.start = guarded_manual_start
        manual._rd_control_mode_start_wrapped = True

    if not install_ui:
        return manager

    # Auto Mix creates a session through _init_session rather than controller.start().
    # Its installed handler resolves this module global at call time.
    import mix_mode

    if not getattr(mix_mode, "_rd_control_mode_start_wrapped", False):
        original_mix_start = mix_mode.start_mix_transactional

        async def guarded_mix_start(app_arg: Any, event: Any, pending: Any) -> bool:
            rd_mode = getattr(app_arg, "rd_control_mode_manager", None)
            if rd_mode is not None and bool(
                getattr(rd_mode, "hands_off", False)
                or getattr(rd_mode, "edge_autonomous", False)
                or getattr(rd_mode, "release_in_progress", False)
            ):
                message = (
                    event.message
                    if hasattr(event, "message") and event.message is not None
                    else event
                )
                await message.answer(
                    "🔓 Режим РД — не лезь включён. Сначала верните контроль заряда; "
                    "текущий Output и уставки не изменены."
                )
                return False
            return bool(await original_mix_start(app_arg, event, pending))

        mix_mode.start_mix_transactional = guarded_mix_start
        mix_mode._rd_control_mode_start_wrapped = True

    original_dashboard_keyboard = app._build_dashboard_keyboard

    def build_dashboard_keyboard(
        is_on: bool,
        user_id: int,
        *,
        back_to_dashboard: bool = False,
    ) -> InlineKeyboardMarkup:
        markup = original_dashboard_keyboard(
            is_on,
            user_id,
            back_to_dashboard=back_to_dashboard,
        )
        if back_to_dashboard:
            return markup
        if not manager.hands_off:
            rows = list(markup.inline_keyboard)
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🔓 Режим РД — не лезь",
                        callback_data="rd_hands_off_enable",
                    )
                ]
            )
            return InlineKeyboardMarkup(inline_keyboard=rows)

        rows = _strip_callbacks(
            markup,
            {"power_toggle", "charge_modes", "menu_off", CHARGE_CALLBACK_DATA, OFF_CALLBACK_DATA},
        )
        primary: list[list[InlineKeyboardButton]] = []
        if is_on:
            primary.append(
                [
                    InlineKeyboardButton(
                        text="⏹ Output OFF",
                        callback_data="rd_hands_off_output_off",
                    )
                ]
            )
        primary.append(
            [
                InlineKeyboardButton(
                    text="🔒 Вернуть контроль заряда",
                    callback_data="rd_hands_off_disable",
                )
            ]
        )
        return InlineKeyboardMarkup(inline_keyboard=primary + rows)

    app._build_dashboard_keyboard = build_dashboard_keyboard

    original_caption = getattr(app, "_compact_dashboard_caption", None)
    if callable(original_caption):

        def compact_dashboard_caption(
            live: Any,
            chart_mode: str,
            mode: str,
            idle_warning: str,
        ) -> str:
            body = original_caption(
                live,
                chart_mode,
                mode,
                "" if manager.hands_off else idle_warning,
            )
            if not manager.hands_off:
                return body
            return (
                "<b>🔓 РЕЖИМ РД — НЕ ЛЕЗЬ</b>\n"
                "Pb-автоматика отключена; бот не меняет Output/уставки.\n"
                f"{body}"
            )

        app._compact_dashboard_caption = compact_dashboard_caption

    @app.router.callback_query(F.data == "rd_hands_off_enable")
    async def _enable_hands_off(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        # Old Telegram messages may still contain the pre-confirmation callback. Never
        # let such a stale button bypass the active-session two-step release flow.
        prompt = getattr(manager, "_active_release_prompt", None)
        if manager._managed_session_active() and callable(prompt):
            await prompt(call)
            return
        await call.answer()
        try:
            await manager.enter_hands_off()
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.message.answer(
            "🔓 <b>Режим РД — не лезь включён.</b>\n"
            "Pb-автоматика и все bot-актуаторы отключены. "
            "Текущий Output и уставки не изменялись.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "rd_hands_off_disable")
    async def _disable_hands_off(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        try:
            await manager.return_pb_control()
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.message.answer(
            "🔒 <b>Контроль заряда возвращён.</b>\n"
            "Pb safety снова активна. Output остаётся подтверждённо OFF; "
            "старый AUTO-сеанс не восстанавливается автоматически.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "rd_hands_off_output_off")
    async def _hands_off_output_off(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        try:
            await manager.operator_output_off(app.ENTITY_MAP.get("switch"))
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.message.answer(
            "⏹ Output подтверждён OFF. Режим РД — не лезь остаётся включённым."
        )

    return manager
