from __future__ import annotations

import asyncio
from typing import Any, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from rd6018_telemetry import telemetry_freshness
from rd_control_mode import RdControlMode, RdControlModeManager
from runtime.safety.runtime_guard import OutputOffNotConfirmed, RuntimeSafetyError


def _managed_active(app: Any) -> bool:
    controller = getattr(app, "charge_controller", None)
    manual = getattr(app, "manual_session_manager", None)
    return bool(
        (controller is not None and getattr(controller, "is_active", False))
        or (manual is not None and getattr(manual, "is_active", False))
    )


async def release_unmanaged_live_output_to_hands_off(
    app: Any,
    manager: RdControlModeManager,
) -> bool:
    """Transfer an already-ON orphan/external Output to durable HANDS_OFF.

    This is the missing recovery boundary between an absent software session and a
    possibly still-armed edge lease.  It never writes Output/V/I.  If the
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
        except asyncio.CancelledError:
            if not committed:
                # The edge release has not been invoked. Restore the exact
                # pre-commit lease-renewal state while PB remains authoritative.
                manager.mode = RdControlMode.PB_MANAGED
                if lease is not None:
                    lease.resume_renewals()
            # After commit, preserve HANDS_OFF and never re-arm/roll back on cancel.
            raise
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
    """Register existing ownership recovery callbacks for this application."""
    if bool(getattr(app, "_rd_ownership_recovery_installed", False)):
        return

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
            "Бот больше не меняет Output/V/I; текущий Output и уставки не переписывались.",
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
