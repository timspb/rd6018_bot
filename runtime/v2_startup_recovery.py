"""V2 startup recovery coordinator.

This is an orchestration boundary only. The supplied V2 application remains the
owner of controller/session/safety/physical semantics; this module preserves the
existing recovery order and delegates to those owners.
"""

from __future__ import annotations

from typing import Any

from diagnostic_persistence import recover_diagnostic_persistence


class V2StartupRecovery:
    def __init__(self, app: Any, managed_mix: Any, managed_live: Any, live_observer: Any = None) -> None:
        self.app = app
        self.managed_mix = managed_mix
        self.managed_live = managed_live
        self.live_observer = live_observer

    async def recover_managed_startup_authority(self) -> bool:
        if not await self.managed_mix.recover_startup():
            return False
        if not await self.managed_live.recover_startup():
            return False
        if self.live_observer is not None and not await self.live_observer.recover_startup():
            return False
        await recover_diagnostic_persistence(self.app)
        return True

    async def replay_deferred_startup_restore(self) -> None:
        """Replay deferred managed restore through the existing safe V2 owner."""
        app = self.app
        controller = app.charge_controller
        live = await app.hass.get_all_live()

        if not bool(getattr(controller, "is_active", False)):
            ok, _msg = controller.try_restore_session(
                app._safe_float(live.get("battery_voltage")),
                app._safe_float(live.get("current")),
                app._safe_float(live.get("ah")),
                output_is_on=(str(live.get("switch", "")).lower() == "on"),
                is_cv=str(live.get("is_cv", "")).lower() == "on",
                is_cc=str(live.get("is_cc", "")).lower() == "on",
            )
            if not ok:
                return
            app._apply_restore_time_corrections(controller, live)
            app.last_checkpoint_time = app.time.time()
            app.logger.info(
                "Deferred startup session state restored after MANAGED authority reconciliation: %s",
                controller.current_stage,
            )

        if app._operator_pause_active():
            app.logger.info("Deferred startup auto-resume skipped: operator pause is active")
            return
        if not app._restore_allows_auto_enable(controller):
            return

        output_state = str(live.get("switch", "")).strip().lower()
        safe_wait_stage = getattr(controller, "STAGE_SAFE_WAIT", None)
        if safe_wait_stage is not None and controller.current_stage == safe_wait_stage:
            if output_state == "off":
                return
            if output_state != "on":
                raise RuntimeError("deferred startup restore cannot resolve SAFE_WAIT Output state")
            confirmed_off = await app.hass.turn_off(app.ENTITY_MAP["switch"])
            if not confirmed_off:
                raise RuntimeError("deferred startup SAFE_WAIT Output OFF was not confirmed")
            return

        if output_state == "on":
            return
        if output_state != "off":
            raise RuntimeError("deferred startup restore cannot resolve canonical Output state")

        raw_temp = live.get("temp_ext")
        if raw_temp is None or str(raw_temp).strip().lower() in {"", "unknown", "unavailable", "none"}:
            raise RuntimeError("deferred startup restore requires fresh battery temperature")
        temp_ext = app._safe_float(raw_temp)
        uv, ui = controller._get_target_v_i(temp_ext)
        await app._apply_phase_protection(uv, ui)
        await app.hass.set_voltage(uv)
        await app.hass.set_current(app._cap_current(ui))
        enabled = await app.hass.turn_on(app.ENTITY_MAP["switch"])
        if not enabled:
            raise RuntimeError("deferred startup safe Output enable was not confirmed")
        app.logger.info(
            "Deferred startup session physically resumed after MANAGED authority reconciliation: %s",
            controller.current_stage,
        )
