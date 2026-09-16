"""Lifecycle orchestration for the preserved V2 runtime.

This module owns only startup/shutdown sequencing and Telegram polling
coordination.  The supplied application object remains the owner of V2
controller, session, safety, persistence, and physical semantics.
"""

from __future__ import annotations

import asyncio
from typing import Any

from runtime.background import start_background_tasks


class V2RuntimeLifecycle:
    """Run the existing V2 lifecycle through an explicit orchestration seam."""

    def __init__(self, app: Any, telegram_runtime: Any) -> None:
        self.app = app
        self.telegram_runtime = telegram_runtime

    async def _periodic_db_cleanup(self) -> None:
        while True:
            await asyncio.sleep(24 * 3600)
            try:
                from database import cleanup_old_records

                await cleanup_old_records()
            except Exception as ex:
                self.app.logger.error("Periodic DB cleanup failed: %s", ex)

    async def on_shutdown(self, _dispatcher: Any) -> None:
        """Preserve the V2 shutdown order without owning domain semantics."""
        app = self.app
        app.logger.info("Shutting down gracefully...")
        try:
            if app.charge_controller.is_active:
                app.charge_controller._save_session(0.0, 0.0, 0.0)
        except Exception as ex:
            app.logger.warning("Failed to save session on shutdown: %s", ex)
        try:
            await app.hass.close()
        except Exception:
            pass
        try:
            from database import close_db

            await close_db()
        except Exception:
            pass
        app.logger.info("Shutdown complete.")

    async def run(self) -> None:
        app = self.app
        await app.init_db()
        app.rotate_if_needed()
        start_background_tasks(self._periodic_db_cleanup)
        try:
            n = app.trim_log_older_than_days(30)
            if n > 0:
                app.logger.info("Trimmed %d old lines from charging_history.log", n)
        except Exception as ex:
            app.logger.warning("trim_log_older_than_days at startup: %s", ex)

        app._load_manual_off_state()
        app._load_operator_pause_state()

        # Preserve the existing V2 restore probe.  Production wraps this call in
        # the startup authority reconciliation before any automatic continuation.
        try:
            live = await app.hass.get_all_live()
            battery_v = app._safe_float(live.get("battery_voltage"))
            current = app._safe_float(live.get("current"))
            ah = app._safe_float(live.get("ah"))
            ovp_triggered = str(live.get("ovp_triggered", "")).lower() == "on"
            ocp_triggered = str(live.get("ocp_triggered", "")).lower() == "on"
            input_voltage = app._safe_float(live.get("input_voltage"), 0.0)
            controller = app.charge_controller
            ok, msg = controller.try_restore_session(
                battery_v,
                current,
                ah,
                output_is_on=(str(live.get("switch", "")).lower() == "on"),
                is_cv=str(live.get("is_cv", "")).lower() == "on",
                is_cc=str(live.get("is_cc", "")).lower() == "on",
            )
            if ok and msg:
                app._apply_restore_time_corrections(controller, live)
                app.last_checkpoint_time = app.time.time()
                temp_ext = app._safe_float(live.get("temp_ext"))
                allow_turn_on = (
                    app._restore_allows_auto_enable(controller)
                    and not ovp_triggered
                    and not ocp_triggered
                    and input_voltage >= app.MIN_INPUT_VOLTAGE
                )
                if app._operator_pause_active():
                    app.logger.info("Auto-resume skipped: operator pause is active")
                elif allow_turn_on:
                    if controller.current_stage == controller.STAGE_SAFE_WAIT:
                        uv, ui = controller._safe_wait_target_v, controller._safe_wait_target_i
                        await app._apply_phase_protection(uv, ui)
                        await app.hass.set_voltage(uv)
                        await app.hass.set_current(app._cap_current(ui))
                        await app.hass.turn_off(app.ENTITY_MAP["switch"])
                    else:
                        uv, ui = controller._get_target_v_i(temp_ext)
                        await app._apply_phase_protection(uv, ui)
                        await app.hass.set_voltage(uv)
                        await app.hass.set_current(app._cap_current(ui))
                        await app.hass.turn_on(app.ENTITY_MAP["switch"])
                    app.log_event(controller.current_stage, battery_v, current, temp_ext, ah, "RESTORE")
                    app._charge_notify(msg)
                    app.logger.info("Session restored: %s", controller.current_stage)
                else:
                    app.logger.info(
                        "Auto-resume skipped: ovp=%s ocp=%s input_v=%.0f",
                        ovp_triggered,
                        ocp_triggered,
                        input_voltage,
                    )
        except Exception as ex:
            app.logger.warning("Auto-resume check failed: %s", ex)

        app.dp.include_router(app.router)
        await app.configure_commands(self.telegram_runtime)
        start_background_tasks(
            app.data_logger,
            app.charge_monitor,
            app.soft_watchdog_loop,
            app.watchdog_loop,
        )
        app.logger.info("RD6018 bot starting")
        app.logger.info(
            "Если появится TelegramConflictError — запущен ещё один экземпляр бота. "
            "Остановите все кроме одного: pgrep -af 'bot.py' && kill <PID>"
        )
        try:
            await app.run_polling(self.telegram_runtime, shutdown_handler=self.on_shutdown)
        finally:
            await app.hass.close()
            app.logger.info("RD6018 bot stopped")
