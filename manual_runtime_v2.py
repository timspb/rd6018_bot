from __future__ import annotations

import asyncio
import json
import math
import os
import time
from typing import Any, Optional

from manual_mode import (
    MANUAL_POLL_SEC,
    ManualChargeRequest,
    ManualSessionManager,
    ManualSessionState,
)
from rd6018_telemetry import as_bool, finite_float


MANUAL_REACH_EPS = 0.02


def _finite_optional(value: Any) -> Optional[float]:
    result = finite_float(value)
    return float(result) if result is not None else None


def _crossed(previous: Optional[float], current: float, target: float) -> bool:
    """Return true when a sampled signal reached or crossed an operator target."""
    if abs(float(current) - float(target)) <= MANUAL_REACH_EPS:
        return True
    if previous is None:
        return False
    lo = min(float(previous), float(current)) - MANUAL_REACH_EPS
    hi = max(float(previous), float(current)) + MANUAL_REACH_EPS
    return lo <= float(target) <= hi


class ProductionManualSessionManager(ManualSessionManager):
    """Production Manual authority with legacy-entry compatibility.

    The old quick ``V I third`` syntax described the third value as "reach this V/I",
    not as a one-sided threshold. Keeping that distinction avoids the unsafe shortcut
    of encoding an equality as both >= and <=. Exact-reach state is persisted next to
    the normal Manual request and is reset across Cooling because an OFF interval breaks
    continuity between samples.

    The legacy persistent ``Manual OFF`` overlay remains an independent kill-condition
    system. When it fires during a managed Manual session, the manager owns the stop so
    software state cannot remain ACTIVE after another runtime path has turned Output off.

    A failed/unconfirmed OFF is special: the session deliberately remains in ARMING
    containment instead of becoming an inactive FAILED session. That keeps the runtime
    safety guard authoritative until physical OFF can actually be proved.
    """

    def __init__(self, app: Any, *, session_file: str = "manual_session_v2.json") -> None:
        self.reach_voltage_v: Optional[float] = None
        self.reach_current_a: Optional[float] = None
        self._previous_voltage_v: Optional[float] = None
        self._previous_current_a: Optional[float] = None
        super().__init__(app, session_file=session_file)

    def _document(self) -> dict[str, Any]:
        document = super()._document()
        document["reach_voltage_v"] = self.reach_voltage_v
        document["reach_current_a"] = self.reach_current_a
        return document

    def _restore_as_interrupted(self) -> None:
        saved_reach_v: Optional[float] = None
        saved_reach_i: Optional[float] = None
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                saved_reach_v = _finite_optional(raw.get("reach_voltage_v"))
                saved_reach_i = _finite_optional(raw.get("reach_current_a"))
            except (OSError, json.JSONDecodeError, TypeError):
                pass
        super()._restore_as_interrupted()
        self.reach_voltage_v = saved_reach_v
        self.reach_current_a = saved_reach_i
        if self.state is ManualSessionState.INTERRUPTED:
            self._persist()

    @staticmethod
    def _validate_reach(value: Optional[float], *, ceiling: float, name: str) -> Optional[float]:
        if value is None:
            return None
        result = float(value)
        if not math.isfinite(result) or result < 0 or result > float(ceiling):
            raise ValueError(f"{name} reach target is outside the manual safety envelope")
        return result

    @staticmethod
    def _off_unconfirmed_detail(value: Any) -> bool:
        text = str(value or "").strip().lower().replace("_", " ")
        return "output off was not confirmed" in text or "output off unconfirmed" in text

    def _preserve_containment_after_denied_enable(self, context: str) -> None:
        """Keep authority if a denied safe-enable could not prove physical OFF.

        SafeOutputCoordinator normally returns a structured denied result rather than
        raising. The base Manual manager maps all denied results to FAILED, which is
        correct only when cleanup is known safe. If its detail says OFF was not
        confirmed, FAILED would make the session inactive while the RD output may still
        be energized. Reclassify that one case to ARMING containment.
        """
        if self.state is not ManualSessionState.FAILED:
            return
        if not self._off_unconfirmed_detail(self.stop_reason):
            return
        self.state = ManualSessionState.ARMING
        if "output_off_unconfirmed" not in self.stop_reason:
            self.stop_reason = f"{context}:{self.stop_reason}:output_off_unconfirmed"
        self.cooling_started_at = None
        self._persist()

    async def _contain_enable_exception(self, context: str, exc: Exception) -> bool:
        confirmed_off = False
        try:
            confirmed_off = bool(await self.app.hass.turn_off())
        except Exception:
            confirmed_off = False
        self.stop_reason = f"{context}:{type(exc).__name__}"
        if confirmed_off:
            self.state = ManualSessionState.FAILED
        else:
            # Do not become inactive while physical output state is unknown. The V2
            # runtime guard treats ARMING as managed authority and keeps trying fail-close.
            self.state = ManualSessionState.ARMING
            self.stop_reason += ":output_off_unconfirmed"
        self.cooling_started_at = None
        self._persist()
        return False

    async def start(
        self,
        request: ManualChargeRequest,
        *,
        reach_voltage_v: Optional[float] = None,
        reach_current_a: Optional[float] = None,
    ) -> bool:
        from charge_logic import MAX_STAGE_CURRENT
        from config import MAX_MANUAL_VOLTAGE

        reach_v = self._validate_reach(
            reach_voltage_v,
            ceiling=float(MAX_MANUAL_VOLTAGE),
            name="voltage",
        )
        reach_i = self._validate_reach(
            reach_current_a,
            ceiling=float(MAX_STAGE_CURRENT),
            name="current",
        )
        self.reach_voltage_v = reach_v
        self.reach_current_a = reach_i
        self._previous_voltage_v = None
        self._previous_current_a = None
        try:
            enabled = await super().start(request)
        except Exception as exc:
            return await self._contain_enable_exception("manual_start_exception", exc)
        if not enabled:
            self._preserve_containment_after_denied_enable("manual_start_denied")
        return enabled

    async def _retire_runner(self) -> None:
        task = self._task
        self._task = None
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def replace(
        self,
        request: ManualChargeRequest,
        *,
        reach_voltage_v: Optional[float] = None,
        reach_current_a: Optional[float] = None,
    ) -> bool:
        """Safely replace an active Manual program through verified OFF -> fresh ON."""
        if bool(getattr(self.app.charge_controller, "is_active", False)):
            raise RuntimeError("automatic charge controller is active")
        if self.is_active:
            if not await self.stop("manual_reconfigure"):
                return False
        await self._retire_runner()
        return await self.start(
            request,
            reach_voltage_v=reach_voltage_v,
            reach_current_a=reach_current_a,
        )

    async def stop(self, reason: str = "operator_stop") -> bool:
        self.stop_reason = str(reason)
        confirmed = False
        try:
            confirmed = bool(await self.app.hass.turn_off())
        except Exception:
            confirmed = False
        if confirmed:
            self.state = ManualSessionState.STOPPED
            self._previous_voltage_v = None
            self._previous_current_a = None
        else:
            # FAILED is intentionally inactive; using it here would tell the runtime
            # guard that nobody owns a potentially still-energized output. Keep a
            # managed containment state until OFF is positively confirmed.
            self.state = ManualSessionState.ARMING
            self.stop_reason = f"{reason}:output_off_unconfirmed"
        self.cooling_started_at = None
        self._persist()
        return confirmed

    async def _enter_cooling(self) -> None:
        self._previous_voltage_v = None
        self._previous_current_a = None
        await super()._enter_cooling()
        # A normal denied OFF from a non-strict/fake adapter must not leave production
        # Manual inactive either. Strict production adapters raise, but keep the state
        # machine correct independently from adapter implementation details.
        if (
            self.state is ManualSessionState.FAILED
            and self.stop_reason == "cooling_output_off_unconfirmed"
        ):
            self.state = ManualSessionState.ARMING
            self._persist()

    async def _resume_after_cooling(self) -> None:
        try:
            await super()._resume_after_cooling()
        except Exception as exc:
            await self._contain_enable_exception("manual_cooling_resume_exception", exc)
        else:
            self._preserve_containment_after_denied_enable("manual_cooling_resume_denied")
        self._previous_voltage_v = None
        self._previous_current_a = None

    def _reach_reason(self, voltage: float, current: float) -> Optional[str]:
        if self.reach_voltage_v is not None and _crossed(
            self._previous_voltage_v,
            voltage,
            self.reach_voltage_v,
        ):
            return "manual_voltage_reached"
        if self.reach_current_a is not None and _crossed(
            self._previous_current_a,
            current,
            self.reach_current_a,
        ):
            return "manual_current_reached"
        return None

    def _legacy_manual_off_reason(
        self,
        *,
        voltage: float,
        current: float,
        now: float,
    ) -> Optional[str]:
        """Mirror the persistent V1 Manual-OFF overlay inside managed Manual state."""
        v_ge = _finite_optional(getattr(self.app, "manual_off_voltage", None))
        v_le = _finite_optional(getattr(self.app, "manual_off_voltage_le", None))
        i_le = _finite_optional(getattr(self.app, "manual_off_current", None))
        i_ge = _finite_optional(getattr(self.app, "manual_off_current_ge", None))
        time_sec = _finite_optional(getattr(self.app, "manual_off_time_sec", None))
        start_time = _finite_optional(getattr(self.app, "manual_off_start_time", None))

        if v_ge is not None and v_le is not None and abs(v_ge - v_le) < 0.01:
            if _crossed(self._previous_voltage_v, voltage, v_ge):
                return "manual_off_voltage_reached"
        else:
            if v_ge is not None and voltage >= v_ge:
                return "manual_off_voltage_ge"
            if v_le is not None and voltage <= v_le:
                return "manual_off_voltage_le"

        if i_le is not None and i_ge is not None and abs(i_le - i_ge) < 0.01:
            if _crossed(self._previous_current_a, current, i_le):
                return "manual_off_current_reached"
        else:
            if i_le is not None and current <= i_le:
                return "manual_off_current_le"
            if i_ge is not None and current >= i_ge:
                return "manual_off_current_ge"

        if (
            time_sec is not None
            and time_sec > 0
            and start_time is not None
            and start_time > 0
            and now - start_time >= time_sec
        ):
            return "manual_off_timer"
        return None

    async def observe_once(self) -> None:
        if not self.is_active or self.request is None:
            return

        live = await self.app.hass.get_all_live()
        voltage = finite_float(live.get("battery_voltage"))
        current = finite_float(live.get("current"))
        if voltage is not None and current is not None and self.state is not ManualSessionState.COOLING:
            now = time.time()
            reason = self._reach_reason(float(voltage), float(current))
            if reason is None:
                reason = self._legacy_manual_off_reason(
                    voltage=float(voltage),
                    current=float(current),
                    now=now,
                )
            if reason is not None:
                await self.stop(reason)
                return

            output_on = as_bool(live.get("switch"))
            if self.state is ManualSessionState.ACTIVE and output_on is False:
                self.state = ManualSessionState.FAILED
                self.stop_reason = "manual_output_off_unexpected"
                self._persist()
                return

            self._previous_voltage_v = float(voltage)
            self._previous_current_a = float(current)

        await super().observe_once()

    async def _run(self) -> None:
        try:
            while self.is_active:
                await self.observe_once()
                if not self.is_active:
                    break
                await asyncio.sleep(MANUAL_POLL_SEC)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.stop_reason = f"manual_runtime_error:{type(exc).__name__}"
            confirmed_off = False
            try:
                confirmed_off = bool(await self.app.hass.turn_off())
            except Exception:
                confirmed_off = False
            if confirmed_off:
                self.state = ManualSessionState.FAILED
            else:
                self.state = ManualSessionState.ARMING
                self.stop_reason += ":output_off_unconfirmed"
            self.cooling_started_at = None
            self._persist()
