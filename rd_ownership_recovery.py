from __future__ import annotations

from typing import Any, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import operator_hmi as hmi
from rd6018_telemetry import telemetry_freshness
from rd_control_mode import RdControlMode, RdControlModeManager
from runtime_safety import OutputOffNotConfirmed, RuntimeSafetyError


def _managed_active(app: Any) -> bool:
    controller = getattr(app, "charge_controller", None)
    manual = getattr(app, "manual_session_manager", None)
    return bool(
        (controller is not None and getattr(controller, "is_active", False))
        or (manual is not None and getattr(manual, "is_active", False))
    )


def _callback_set(markup: InlineKeyboardMarkup) -> set[str]:
    return {
        str(getattr(button, "callback_data", "") or "")
        for row in markup.inline_keyboard
        for button in row
        if getattr(button, "callback_data", None)
    }


def _prepend_unique(
    markup: InlineKeyboardMarkup,
    rows: list[list[InlineKeyboardButton]],
) -> InlineKeyboardMarkup:
    existing = _callback_set(markup)
    filtered: list[list[InlineKeyboardButton]] = []
    for row in rows:
        unique = [
            button
            for button in row
            if not button.callback_data or str(button.callback_data) not in existing
        ]
        if unique:
            filtered.append(unique)
            existing.update(
                str(button.callback_data)
                for button in unique
                if button.callback_data
            )
    return InlineKeyboardMarkup(
        inline_keyboard=filtered + [list(row) for row in markup.inline_keyboard]
    )


def _append_unique(
    markup: InlineKeyboardMarkup,
    rows: list[list[InlineKeyboardButton]],
) -> InlineKeyboardMarkup:
    existing = _callback_set(markup)
    result = [list(row) for row in markup.inline_keyboard]
    for row in rows:
        unique = [
            button
            for button in row
            if not button.callback_data or str(button.callback_data) not in existing
        ]
        if unique:
            result.append(unique)
            existing.update(
                str(button.callback_data)
                for button in unique
                if button.callback_data
            )
    return InlineKeyboardMarkup(inline_keyboard=result)


async def release_unmanaged_live_output_to_hands_off(
    app: Any,
    manager: RdControlModeManager,
) -> bool:
    """Transfer an already-ON orphan/external Output to durable HANDS_OFF.

    This is the missing recovery boundary between an absent software session and a
    possibly still-armed edge lease.  It never writes Output/V/I/OVP/OCP.  If the
    edge lease is armed, the dedicated live ownership-release command is required.
    If the edge is already unarmed, fresh direct edge/Output evidence is still required
    before software commits HANDS_OFF.

    After the durable HANDS_OFF commit, an ambiguous edge ACK never rolls software
    authority back to PB_MANAGED; the edge command may have executed and the local
    watchdog may still turn Output OFF.
    """
    async with manager._transition_lock:
        if manager.hands_off:
            return True
        if bool(getattr(manager.guard, "_off_unconfirmed", False)):
            raise RuntimeSafetyError(
                "RD HANDS_OFF blocked: previous Output OFF remains unconfirmed"
            )
        if _managed_active(app):
            raise RuntimeSafetyError(
                "RD HANDS_OFF blocked: active managed charge requires the session-bound release flow"
            )

        guard = manager.guard
        live = await guard._raw_live()
        evidence = guard._output_evidence(live)
        try:
            fresh = bool(telemetry_freshness(live, ("switch",)).valid)
        except Exception:
            fresh = False
        if not fresh or evidence.state is not True:
            raise RuntimeSafetyError(
                "live HANDS_OFF recovery requires fresh confirmed Output ON"
            )

        lease = None
        prepared = None
        edge_armed = False
        committed = False
        manager._release_in_progress = True
        try:
            if bool(getattr(guard, "edge_lease_enforced", False)):
                lease = getattr(guard, "edge_safety_lease", None)
                if lease is None:
                    raise RuntimeSafetyError(
                        "live HANDS_OFF recovery requires the configured edge safety lease"
                    )
                state = await lease.read_state()
                if state.boot_quarantine:
                    raise RuntimeSafetyError(
                        "live HANDS_OFF recovery blocked: edge boot quarantine is active"
                    )
                if state.tripped:
                    raise RuntimeSafetyError(
                        "live HANDS_OFF recovery blocked: edge lease trip is latched"
                    )
                if not lease._fresh_modbus(state):
                    raise RuntimeSafetyError(
                        f"live HANDS_OFF recovery blocked: RD Modbus is stale at edge ({state.modbus_age_s:.1f}s)"
                    )
                edge_armed = bool(state.armed)
                if edge_armed:
                    lease.suspend_renewals()
                    prepared = await lease.prepare_hands_off_release()

            # Commit software ownership before the live edge command.  From here on
            # PB automation must not silently return even if the positive ACK is lost.
            manager._write_mode(RdControlMode.HANDS_OFF)
            manager.mode = RdControlMode.HANDS_OFF
            committed = True
            guard._orphan_output_seen_at = None
            manager._clear_stale_auto_restore_authority()

            if edge_armed and lease is not None:
                try:
                    await lease.release_to_hands_off(
                        expected_generation=getattr(prepared, "generation", None)
                    )
                except Exception as exc:
                    raise RuntimeSafetyError(
                        "RD HANDS_OFF is durably active, but edge ownership release was not "
                        f"positively acknowledged ({exc}); local watchdog may still turn Output OFF"
                    ) from exc
            return True
        except Exception:
            if not committed:
                manager.mode = RdControlMode.PB_MANAGED
                if lease is not None:
                    lease.resume_renewals()
            raise
        finally:
            manager._release_in_progress = False


def install_rd_ownership_recovery(
    app: Any,
    manager: RdControlModeManager,
) -> None:
    """Compose ownership recovery into the *final* semantic operator HMI.

    Older ownership installers wrap ``app._build_dashboard_keyboard`` before the final
    operator HMI replaces it.  This composer runs after ``install_operator_hmi`` and
    wraps the authoritative ``operator_hmi.build_operator_keyboard`` instead, so the
    production panel cannot lose HANDS_OFF/release/adoption controls through install
    order.
    """
    if bool(getattr(app, "_rd_ownership_recovery_installed", False)):
        return

    original_keyboard = hmi.build_operator_keyboard

    def build_operator_keyboard(app_arg: Any, state: hmi.OperatorHmiState) -> InlineKeyboardMarkup:
        markup = original_keyboard(app_arg, state)

        if state.process_state is hmi.HmiProcessState.IDLE and manager.pb_managed:
            return _append_unique(
                markup,
                [[InlineKeyboardButton(
                    text="🔓 Режим РД — не лезь",
                    callback_data="rd_ownership_hands_off",
                )]],
            )

        if (
            state.process_state is hmi.HmiProcessState.CONTAINMENT
            and bool(state.output_on)
            and manager.pb_managed
            and not _managed_active(app_arg)
        ):
            actions: list[list[InlineKeyboardButton]] = []
            adoption = getattr(app_arg, "rd_managed_live_adoption", None)
            if adoption is not None and not bool(getattr(adoption, "active", False)) and not bool(
                getattr(adoption, "off_pending", False)
            ):
                actions.append([
                    InlineKeyboardButton(
                        text="✅ Принять управление",
                        callback_data="rd_ownership_adopt",
                    )
                ])
            actions.extend(
                [
                    [InlineKeyboardButton(
                        text="🔓 Не лезть",
                        callback_data="rd_ownership_hands_off",
                    )],
                    [InlineKeyboardButton(
                        text="⏹ Output OFF",
                        callback_data="rd_ownership_output_off",
                    )],
                ]
            )
            return _prepend_unique(markup, actions)

        if state.process_state is hmi.HmiProcessState.HANDS_OFF:
            if state.output_on:
                return markup
            return _prepend_unique(
                markup,
                [[InlineKeyboardButton(
                    text="🔒 Вернуть контроль заряда",
                    callback_data="rd_hands_off_disable",
                )]],
            )

        return markup

    hmi.build_operator_keyboard = build_operator_keyboard
    app._rd_ownership_recovery_installed = True

    @app.router.callback_query(F.data == "rd_ownership_hands_off")
    async def _ownership_hands_off(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if _managed_active(app):
            prompt = getattr(manager, "_active_release_prompt", None)
            if callable(prompt):
                await prompt(call)
                return
            await call.answer(
                "Активная managed-сессия требует отдельного подтверждения release",
                show_alert=True,
            )
            return
        try:
            live = await manager.guard._raw_live()
            evidence = manager.guard._output_evidence(live)
            if evidence.state is True:
                await release_unmanaged_live_output_to_hands_off(app, manager)
            else:
                await manager.enter_hands_off()
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.answer("Режим РД включён")
        await call.message.answer(
            "🔓 <b>Режим РД — не лезь включён.</b>\n"
            "Бот больше не меняет Output/V/I/OVP/OCP; текущий Output и уставки не переписывались.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "rd_ownership_adopt")
    async def _ownership_adopt(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if _managed_active(app):
            await call.answer("Managed-сессия уже активна", show_alert=True)
            return
        try:
            if not manager.hands_off:
                await release_unmanaged_live_output_to_hands_off(app, manager)
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.answer("Ownership изолирован")
        await call.message.answer(
            "✅ <b>Output переведён в безопасный HANDS_OFF boundary без изменения уставок.</b>\n"
            "Теперь можно выполнить D061 managed adoption.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✅ Продолжить подхват",
                        callback_data="rd_managed_adopt",
                    )],
                    [InlineKeyboardButton(
                        text="Оставить — не лезть",
                        callback_data="operator_refresh",
                    )],
                ]
            ),
        )

    @app.router.callback_query(F.data == "rd_ownership_output_off")
    async def _ownership_output_off(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if manager.hands_off:
            await call.answer("Используйте HANDS_OFF Output OFF", show_alert=True)
            return
        if _managed_active(app):
            await call.answer("Активную managed-сессию останавливайте штатным Stop", show_alert=True)
            return
        try:
            await manager.guard._ensure_output_off(
                "explicit operator shutdown of unmanaged Output",
                app.ENTITY_MAP.get("switch"),
            )
            await manager.guard._disarm_edge_lease_best_effort()
        except OutputOffNotConfirmed as exc:
            await call.answer(str(exc), show_alert=True)
            return
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.answer("Output OFF подтверждён")
        await call.message.answer("⏹ Output подтверждён OFF. Pb-control остаётся активным.")
