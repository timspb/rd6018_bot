from __future__ import annotations

import asyncio
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional

from charge_logic import MAX_STAGE_CURRENT, OCP_OFFSET, OVP_OFFSET
from config import MAX_MANUAL_VOLTAGE
from rd6018_telemetry import RegulationMode, finite_float, resolve_regulation


MANUAL_SESSION_FILE = "manual_session_v2.json"
MANUAL_DELTA_BLANKING_SEC = 120.0
MANUAL_DELTA_CONFIRM_COUNT = 3
MANUAL_DELTA_CONFIRM_INTERVAL_SEC = 60.0
MANUAL_POLL_SEC = 5.0
MANUAL_COOLING_PAUSE_C = 40.0
MANUAL_COOLING_RESUME_C = 35.0
MANUAL_TEMP_CRITICAL_C = 45.0


class ManualSessionState(str, Enum):
    IDLE = "idle"
    ARMING = "arming"
    ACTIVE = "active"
    COOLING = "cooling"
    INTERRUPTED = "interrupted"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class ManualStopConditions:
    max_active_seconds: Optional[float] = None
    voltage_ge_v: Optional[float] = None
    voltage_le_v: Optional[float] = None
    current_ge_a: Optional[float] = None
    current_le_a: Optional[float] = None
    delta: Optional[float] = None

    def __post_init__(self) -> None:
        numeric = (
            self.max_active_seconds,
            self.voltage_ge_v,
            self.voltage_le_v,
            self.current_ge_a,
            self.current_le_a,
            self.delta,
        )
        for value in numeric:
            if value is not None and not math.isfinite(float(value)):
                raise ValueError("manual stop conditions must be finite")
        if self.max_active_seconds is not None and self.max_active_seconds <= 0:
            raise ValueError("max_active_seconds must be positive")
        if self.delta is not None and self.delta <= 0:
            raise ValueError("delta must be positive when enabled")


@dataclass(frozen=True)
class ManualChargeRequest:
    voltage_v: float
    current_a: float
    stop: ManualStopConditions = ManualStopConditions()
    battery_id: str = ""
    capacity_ah: Optional[float] = None
    notes: str = ""

    def __post_init__(self) -> None:
        voltage = float(self.voltage_v)
        current = float(self.current_a)
        if not math.isfinite(voltage) or not (0.0 < voltage <= float(MAX_MANUAL_VOLTAGE)):
            raise ValueError(f"manual voltage must be >0 and <= {MAX_MANUAL_VOLTAGE:.1f}V")
        if not math.isfinite(current) or not (0.0 < current <= float(MAX_STAGE_CURRENT)):
            raise ValueError(f"manual current must be >0 and <= {MAX_STAGE_CURRENT:.1f}A")
        if self.capacity_ah is not None and (
            not math.isfinite(float(self.capacity_ah)) or self.capacity_ah <= 0
        ):
            raise ValueError("capacity_ah must be positive when present")

    @property
    def ovp_v(self) -> float:
        return float(self.voltage_v) + float(OVP_OFFSET)

    @property
    def ocp_a(self) -> float:
        return float(self.current_a) + float(OCP_OFFSET)


class ManualSessionManager:
    """Explicit manual authority: operator rules + non-bypassable hard safety.

    No Pb chemistry transition is executed here.  A configured timer/delta/threshold is
    an operator stop condition, not an automatic recipe decision.  OVP/OCP are always
    derived from the requested V/I and are never user-overridable.
    """

    def __init__(self, app: Any, *, session_file: str = MANUAL_SESSION_FILE) -> None:
        self.app = app
        self.session_file = session_file
        self.state = ManualSessionState.IDLE
        self.request: Optional[ManualChargeRequest] = None
        self.started_at = 0.0
        self.paused_total_s = 0.0
        self.cooling_started_at: Optional[float] = None
        self.stop_reason = ""
        self._task: Optional[asyncio.Task] = None
        self._vmax: Optional[float] = None
        self._imin: Optional[float] = None
        self._delta_confirmations = 0
        self._last_delta_confirmation = 0.0
        self._restore_as_interrupted()

    @property
    def is_active(self) -> bool:
        return self.state in {
            ManualSessionState.ARMING,
            ManualSessionState.ACTIVE,
            ManualSessionState.COOLING,
        }

    @property
    def active_elapsed_s(self) -> float:
        if self.started_at <= 0:
            return 0.0
        now = time.time()
        pause = self.paused_total_s
        if self.cooling_started_at is not None:
            pause += max(0.0, now - self.cooling_started_at)
        return max(0.0, now - self.started_at - pause)

    def _document(self) -> dict[str, Any]:
        return {
            "version": 2,
            "state": self.state.value,
            "request": asdict(self.request) if self.request is not None else None,
            "started_at": self.started_at,
            "paused_total_s": self.paused_total_s,
            "cooling_started_at": self.cooling_started_at,
            "stop_reason": self.stop_reason,
            "saved_at": time.time(),
        }

    def _persist(self) -> None:
        tmp = f"{self.session_file}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._document(), handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.session_file)
        except OSError:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def _restore_as_interrupted(self) -> None:
        if not os.path.exists(self.session_file):
            return
        try:
            with open(self.session_file, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError):
            return
        request_raw = raw.get("request")
        if isinstance(request_raw, dict):
            stop_raw = request_raw.get("stop") or {}
            try:
                self.request = ManualChargeRequest(
                    voltage_v=float(request_raw["voltage_v"]),
                    current_a=float(request_raw["current_a"]),
                    stop=ManualStopConditions(**stop_raw),
                    battery_id=str(request_raw.get("battery_id") or ""),
                    capacity_ah=request_raw.get("capacity_ah"),
                    notes=str(request_raw.get("notes") or ""),
                )
            except (KeyError, TypeError, ValueError):
                self.request = None
        previous = str(raw.get("state") or "")
        if previous in {
            ManualSessionState.ARMING.value,
            ManualSessionState.ACTIVE.value,
            ManualSessionState.COOLING.value,
        }:
            # A process restart never silently re-energizes Manual.  The persisted
            # request remains available for operator review/re-authorization.
            self.state = ManualSessionState.INTERRUPTED
            self.stop_reason = "process_restart_requires_operator_reauthorization"
            self.started_at = float(raw.get("started_at") or 0.0)
            self.paused_total_s = float(raw.get("paused_total_s") or 0.0)
            self.cooling_started_at = None
            self._persist()

    def _reset_delta_tracking(self) -> None:
        self._vmax = None
        self._imin = None
        self._delta_confirmations = 0
        self._last_delta_confirmation = 0.0

    async def start(self, request: ManualChargeRequest) -> bool:
        if self.is_active:
            raise RuntimeError("manual session is already active")
        if bool(getattr(self.app.charge_controller, "is_active", False)):
            raise RuntimeError("automatic charge controller is active")

        self.request = request
        self.state = ManualSessionState.ARMING
        self.started_at = time.time()
        self.paused_total_s = 0.0
        self.cooling_started_at = None
        self.stop_reason = ""
        self._reset_delta_tracking()
        self._persist()

        result = await self.app.hass.safe_enable_output(
            voltage_v=request.voltage_v,
            current_a=request.current_a,
            ovp_v=request.ovp_v,
            ocp_a=request.ocp_a,
            recipe_voltage_ceiling_v=float(MAX_MANUAL_VOLTAGE),
        )
        if not result.enabled:
            self.state = ManualSessionState.FAILED
            self.stop_reason = result.detail or "safe_enable_failed"
            self._persist()
            return False

        self.state = ManualSessionState.ACTIVE
        self._persist()
        self._task = asyncio.create_task(self._run(), name="rd6018-manual-session")
        return True

    async def stop(self, reason: str = "operator_stop") -> bool:
        self.stop_reason = str(reason)
        confirmed = False
        try:
            confirmed = bool(await self.app.hass.turn_off())
        finally:
            self.state = ManualSessionState.STOPPED if confirmed else ManualSessionState.FAILED
            self.cooling_started_at = None
            self._persist()
        return confirmed

    async def _enter_cooling(self) -> None:
        if self.state is ManualSessionState.COOLING:
            return
        if not await self.app.hass.turn_off():
            self.state = ManualSessionState.FAILED
            self.stop_reason = "cooling_output_off_unconfirmed"
            self._persist()
            return
        self.state = ManualSessionState.COOLING
        self.cooling_started_at = time.time()
        self._delta_confirmations = 0
        self._last_delta_confirmation = 0.0
        self._persist()

    async def _resume_after_cooling(self) -> None:
        if self.state is not ManualSessionState.COOLING or self.request is None:
            return
        now = time.time()
        if self.cooling_started_at is not None:
            self.paused_total_s += max(0.0, now - self.cooling_started_at)
        self.cooling_started_at = None
        self.state = ManualSessionState.ARMING
        self._persist()
        result = await self.app.hass.safe_enable_output(
            voltage_v=self.request.voltage_v,
            current_a=self.request.current_a,
            ovp_v=self.request.ovp_v,
            ocp_a=self.request.ocp_a,
            recipe_voltage_ceiling_v=float(MAX_MANUAL_VOLTAGE),
        )
        if not result.enabled:
            self.state = ManualSessionState.FAILED
            self.stop_reason = result.detail or "cooling_resume_failed"
            self._persist()
            return
        self.state = ManualSessionState.ACTIVE
        # Cooling breaks continuity-dependent delta confirmation, but extrema remain
        # useful as historical diagnostics only; start a fresh stop-condition segment.
        self._reset_delta_tracking()
        self._persist()

    def _threshold_reason(self, voltage: float, current: float) -> Optional[str]:
        assert self.request is not None
        stop = self.request.stop
        if stop.max_active_seconds is not None and self.active_elapsed_s >= stop.max_active_seconds:
            return "manual_time_limit"
        if stop.voltage_ge_v is not None and voltage >= stop.voltage_ge_v:
            return "manual_voltage_ge"
        if stop.voltage_le_v is not None and voltage <= stop.voltage_le_v:
            return "manual_voltage_le"
        if stop.current_ge_a is not None and current >= stop.current_ge_a:
            return "manual_current_ge"
        if stop.current_le_a is not None and current <= stop.current_le_a:
            return "manual_current_le"
        return None

    def _delta_reason(self, live: dict[str, Any], *, now: float) -> Optional[str]:
        assert self.request is not None
        threshold = self.request.stop.delta
        if threshold is None or now - self.started_at < MANUAL_DELTA_BLANKING_SEC:
            return None

        voltage = finite_float(live.get("battery_voltage"))
        current = finite_float(live.get("current"))
        if voltage is None or current is None:
            return None
        mode = resolve_regulation(live)
        candidate = False
        if mode is RegulationMode.CV:
            if self._imin is None or current < self._imin:
                self._imin = current
                self._delta_confirmations = 0
                self._last_delta_confirmation = 0.0
            elif current >= self._imin + threshold:
                candidate = True
        elif mode is RegulationMode.CC:
            if self._vmax is None or voltage > self._vmax:
                self._vmax = voltage
                self._delta_confirmations = 0
                self._last_delta_confirmation = 0.0
            elif voltage <= self._vmax - threshold:
                candidate = True
        else:
            self._delta_confirmations = 0
            return None

        if not candidate:
            self._delta_confirmations = 0
            return None
        if (
            self._last_delta_confirmation
            and now - self._last_delta_confirmation < MANUAL_DELTA_CONFIRM_INTERVAL_SEC
        ):
            return None
        self._last_delta_confirmation = now
        self._delta_confirmations += 1
        if self._delta_confirmations >= MANUAL_DELTA_CONFIRM_COUNT:
            return "manual_delta_confirmed"
        return None

    async def observe_once(self) -> None:
        if not self.is_active or self.request is None:
            return
        live = await self.app.hass.get_all_live()
        temp = finite_float(live.get("temp_ext"))
        if temp is None:
            # V2 runtime safety already fails closed on missing critical telemetry.
            return
        if temp >= MANUAL_TEMP_CRITICAL_C:
            await self.stop("manual_critical_battery_temperature")
            return
        if self.state is ManualSessionState.COOLING:
            if temp <= MANUAL_COOLING_RESUME_C:
                await self._resume_after_cooling()
            return
        if temp >= MANUAL_COOLING_PAUSE_C:
            await self._enter_cooling()
            return

        voltage = finite_float(live.get("battery_voltage"))
        current = finite_float(live.get("current"))
        if voltage is None or current is None:
            return
        reason = self._threshold_reason(voltage, current)
        if reason is None:
            reason = self._delta_reason(live, now=time.time())
        if reason is not None:
            await self.stop(reason)

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
            try:
                await self.app.hass.turn_off()
            finally:
                self.state = ManualSessionState.FAILED
                self._persist()

    async def start_from_legacy_ui(self, message: Any, user_id: int, params: dict[str, float]) -> None:
        """Compatibility adapter for the existing 5-step Custom dialog.

        The old dialog's delta/time values become explicit operator stop conditions;
        they no longer grant chemistry/FSM authority.  A native V2 Manual UI can later
        expose the same request model without the legacy dialog's 17.0 V presentation
        limit.
        """
        self.app.last_chat_id = message.chat.id
        self.app.last_user_id = message.from_user.id if message.from_user else user_id
        request = ManualChargeRequest(
            voltage_v=float(params["main_voltage"]),
            current_a=float(params["main_current"]),
            stop=ManualStopConditions(
                max_active_seconds=float(params["time_limit"]) * 3600.0,
                delta=float(params["delta"]),
            ),
            capacity_ah=float(params.get("capacity") or 0.0) or None,
            notes="legacy Custom UI compatibility adapter",
        )
        try:
            enabled = await self.start(request)
        except (RuntimeError, ValueError) as exc:
            await message.answer(f"❌ Ручной режим не запущен: {exc}")
            return
        if not enabled:
            await message.answer(
                "❌ Ручной режим не запущен: безопасное включение RD6018 не подтверждено."
            )
            return
        await message.answer(
            "<b>🛠 Ручной режим запущен</b>\n"
            f"U = {request.voltage_v:.2f} V\n"
            f"I = {request.current_a:.2f} A\n"
            f"OVP = {request.ovp_v:.2f} V (рассчитано)\n"
            f"OCP = {request.ocp_a:.2f} A (рассчитано)\n"
            "Автоматическая химическая FSM отключена; действуют только заданные "
            "условия остановки и неотключаемая безопасность.",
        )
