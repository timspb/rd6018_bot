from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from pathlib import Path
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional

from charge_logic import MAX_STAGE_CURRENT, OCP_OFFSET, OVP_OFFSET
from config import MAX_MANUAL_VOLTAGE
from rd6018_telemetry import RegulationMode, finite_float, resolve_regulation
from runtime.charge.profiles.manual import ManualChargeProfile, load_manual_profile


MANUAL_SESSION_FILE = "manual_session_v2.json"
MANUAL_DELTA_BLANKING_SEC = 120.0
MANUAL_DELTA_CONFIRM_COUNT = 3
MANUAL_DELTA_CONFIRM_INTERVAL_SEC = 60.0
MANUAL_POLL_SEC = 5.0
MANUAL_COOLING_PAUSE_C = 40.0
MANUAL_COOLING_RESUME_C = 35.0
MANUAL_TEMP_CRITICAL_C = 45.0
MANUAL_MIX_VOLTAGE_THRESHOLD_V = 15.8
MANUAL_MIX_FINISH_HOLD_SEC = 2 * 60 * 60
MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A = 0.30

logger = logging.getLogger("rd6018.manual")


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
    profile: Optional[ManualChargeProfile] = None
    stage: str = "main"

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
        if self.stage not in {"main", "mix"}:
            raise ValueError("manual stage must be main or mix")

    @classmethod
    def from_profile(cls, profile: ManualChargeProfile, *, battery_id: str = "", capacity_ah: Optional[float] = None) -> "ManualChargeRequest":
        return cls(
            voltage_v=profile.main.voltage_v,
            current_a=profile.main.current_a,
            battery_id=battery_id,
            capacity_ah=capacity_ah,
            notes="configured staged Manual profile",
            profile=profile,
            stage="main",
        )

    @property
    def ovp_v(self) -> float:
        return float(self.voltage_v) + float(OVP_OFFSET)

    @property
    def ocp_a(self) -> float:
        return float(self.current_a) + float(OCP_OFFSET)

    @property
    def operation_mode(self) -> str:
        return self.stage if self.profile is not None else ("mix" if float(self.voltage_v) >= MANUAL_MIX_VOLTAGE_THRESHOLD_V else "main")

    @property
    def operation_mode_label(self) -> str:
        return "Ручной МИКС" if self.operation_mode == "mix" else "Ручной Основной"


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
        self.finish_hold_started_at: Optional[float] = None
        self.main_min_confirmations = 0
        self.main_min_hold_started_at: Optional[float] = None
        self._last_main_min_confirmation = 0.0
        self.main_tail_current_threshold_a = MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A
        self._restore_as_interrupted()

    def _transition_state(self, new_state: ManualSessionState, reason: str) -> None:
        old_state = self.state
        self.state = new_state
        if old_state is not new_state:
            logger.info(
                "MANUAL_TRANSITION old=%s new=%s reason=%s owner=manual timestamp=%.3f",
                old_state.value,
                new_state.value,
                reason,
                time.time(),
            )

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
            "finish_hold_started_at": self.finish_hold_started_at,
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
                profile = None
                if isinstance(request_raw.get("profile"), dict):
                    profile = load_manual_profile(Path(__file__).resolve().parent / "config" / "charge" / "manual.yaml")
                self.request = ManualChargeRequest(
                    voltage_v=float(request_raw["voltage_v"]),
                    current_a=float(request_raw["current_a"]),
                    stop=ManualStopConditions(**stop_raw),
                    battery_id=str(request_raw.get("battery_id") or ""),
                    capacity_ah=request_raw.get("capacity_ah"),
                    notes=str(request_raw.get("notes") or ""),
                    profile=profile,
                    stage=str(request_raw.get("stage") or "main"),
                )
            except (KeyError, TypeError, ValueError):
                self.request = None
        previous = str(raw.get("state") or "")
        saved_hold = raw.get("finish_hold_started_at")
        if saved_hold is not None:
            try:
                self.finish_hold_started_at = float(saved_hold)
            except (TypeError, ValueError):
                self.finish_hold_started_at = None
        if previous in {
            ManualSessionState.ARMING.value,
            ManualSessionState.ACTIVE.value,
            ManualSessionState.COOLING.value,
        }:
            # A process restart never silently re-energizes Manual.  The persisted
            # request remains available for operator review/re-authorization.
            self._transition_state(
                ManualSessionState.INTERRUPTED,
                "process_restart_requires_operator_reauthorization",
            )
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
        self._transition_state(ManualSessionState.ARMING, "operator_start")
        self.started_at = time.time()
        self.paused_total_s = 0.0
        self.cooling_started_at = None
        self.stop_reason = ""
        self._reset_delta_tracking()
        self.main_min_confirmations = 0
        self.main_min_hold_started_at = None
        self._last_main_min_confirmation = 0.0
        self.finish_hold_started_at = None
        self._persist()

        result = await self.app.hass.safe_enable_output(
            voltage_v=request.voltage_v,
            current_a=request.current_a,
            ovp_v=request.ovp_v,
            ocp_a=request.ocp_a,
            recipe_voltage_ceiling_v=float(MAX_MANUAL_VOLTAGE),
        )
        if not result.enabled:
            self.stop_reason = result.detail or "safe_enable_failed"
            self._transition_state(ManualSessionState.FAILED, self.stop_reason)
            self._persist()
            return False

        self._transition_state(ManualSessionState.ACTIVE, "safe_enable_confirmed")
        self._persist()
        self._task = asyncio.create_task(self._run(), name="rd6018-manual-session")
        return True

    async def stop(self, reason: str = "operator_stop") -> bool:
        self.stop_reason = str(reason)
        confirmed = False
        try:
            confirmed = bool(await self.app.hass.turn_off())
        finally:
            self._transition_state(
                ManualSessionState.STOPPED if confirmed else ManualSessionState.FAILED,
                self.stop_reason,
            )
            self.cooling_started_at = None
            self._persist()
        return confirmed

    async def _enter_cooling(self) -> None:
        if self.state is ManualSessionState.COOLING:
            return
        if not await self.app.hass.turn_off():
            self.stop_reason = "cooling_output_off_unconfirmed"
            self._transition_state(ManualSessionState.FAILED, self.stop_reason)
            self._persist()
            return
        self._transition_state(ManualSessionState.COOLING, "thermal_pause")
        self.cooling_started_at = time.time()
        self._delta_confirmations = 0
        self._last_delta_confirmation = 0.0
        self.finish_hold_started_at = None
        self._persist()

    async def _resume_after_cooling(self) -> None:
        if self.state is not ManualSessionState.COOLING or self.request is None:
            return
        now = time.time()
        if self.cooling_started_at is not None:
            self.paused_total_s += max(0.0, now - self.cooling_started_at)
        self.cooling_started_at = None
        self._transition_state(ManualSessionState.ARMING, "cooling_resume_prepare")
        self._persist()
        result = await self.app.hass.safe_enable_output(
            voltage_v=self.request.voltage_v,
            current_a=self.request.current_a,
            ovp_v=self.request.ovp_v,
            ocp_a=self.request.ocp_a,
            recipe_voltage_ceiling_v=float(MAX_MANUAL_VOLTAGE),
        )
        if not result.enabled:
            self.stop_reason = result.detail or "cooling_resume_failed"
            self._transition_state(ManualSessionState.FAILED, self.stop_reason)
            self._persist()
            return
        self._transition_state(ManualSessionState.ACTIVE, "cooling_resume_confirmed")
        # Cooling breaks continuity-dependent delta confirmation, but extrema remain
        # useful as historical diagnostics only; start a fresh stop-condition segment.
        self._reset_delta_tracking()
        self.finish_hold_started_at = None
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
        if self.request.operation_mode != "mix":
            return None
        threshold = self.request.stop.delta
        if self.request.profile is not None:
            threshold = (
                self.request.profile.mix.delta_current_a
                if resolve_regulation(live) is RegulationMode.CV
                else self.request.profile.mix.delta_voltage_v
            )
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
                logger.info(
                    "MANUAL_EVIDENCE kind=minimum event=update mode=CV value=%.3f timestamp=%.3f",
                    current,
                    now,
                )
            elif current >= self._imin + threshold:
                candidate = True
        elif mode is RegulationMode.CC:
            if self._vmax is None or voltage > self._vmax:
                self._vmax = voltage
                self._delta_confirmations = 0
                self._last_delta_confirmation = 0.0
                logger.info(
                    "MANUAL_EVIDENCE kind=maximum event=update mode=CC value=%.3f timestamp=%.3f",
                    voltage,
                    now,
                )
            elif voltage <= self._vmax - threshold:
                candidate = True
        else:
            self._delta_confirmations = 0
            return None

        if not candidate:
            self._delta_confirmations = 0
            return None
        confirmation_interval = (
            self.request.profile.mix.confirmation_interval_seconds
            if self.request.profile is not None
            else MANUAL_DELTA_CONFIRM_INTERVAL_SEC
        )
        confirmation_count = (
            self.request.profile.mix.confirmation_count
            if self.request.profile is not None
            else MANUAL_DELTA_CONFIRM_COUNT
        )
        if (
            self._last_delta_confirmation
            and now - self._last_delta_confirmation < confirmation_interval
        ):
            return None
        self._last_delta_confirmation = now
        self._delta_confirmations += 1
        logger.info(
            "MANUAL_EVIDENCE kind=delta event=confirmation mode=%s count=%d reference=%.3f threshold=%.3f timestamp=%.3f",
            mode.value,
            self._delta_confirmations,
            self._imin if mode is RegulationMode.CV else self._vmax,
            threshold,
            now,
        )
        if self._delta_confirmations >= confirmation_count:
            return "manual_delta_confirmed"
        return None

    def _main_tail_reason(self, live: dict[str, Any]) -> Optional[str]:
        assert self.request is not None
        if self.request.operation_mode != "main":
            return None
        voltage = finite_float(live.get("battery_voltage"))
        current = finite_float(live.get("current"))
        if voltage is None or current is None:
            return None
        if resolve_regulation(live) is not RegulationMode.CV:
            return None
        if voltage < float(self.request.voltage_v) - 0.20:
            return None
        if self._imin is None or current < self._imin:
            self._imin = current
            logger.info(
                "MANUAL_EVIDENCE kind=minimum event=update mode=CV value=%.3f timestamp=%.3f",
                current,
                time.time(),
            )
        threshold = (
            self.request.profile.main.minimum_current_a
            if self.request.profile is not None
            else self.main_tail_current_threshold_a
        )
        if threshold is not None and current <= float(threshold):
            if self.request.profile is None:
                return "manual_main_cv_imin"
            interval = self.request.profile.main.confirmation_interval_seconds
            now = time.time()
            if self._last_main_min_confirmation and now - self._last_main_min_confirmation < interval:
                return None
            self._last_main_min_confirmation = now
            self.main_min_confirmations += 1
            required = self.request.profile.main.confirmation_count
            if self.main_min_confirmations >= required:
                if self.main_min_hold_started_at is None:
                    self.main_min_hold_started_at = time.time()
                    return None
                if time.time() - self.main_min_hold_started_at >= self.request.profile.main.hold_seconds:
                    return "manual_main_to_mix"
        return None

    async def _advance_profile_to_mix(self) -> None:
        assert self.request is not None and self.request.profile is not None
        stage = self.request.profile.mix
        # Reuse the existing verified OFF -> fresh enable path.  The stage change
        # never introduces a second actuator owner or a direct programming path.
        if not await self.stop("manual_main_hold_complete"):
            return
        self.request = ManualChargeRequest(
            voltage_v=stage.voltage_v,
            current_a=stage.current_a,
            battery_id=self.request.battery_id,
            capacity_ah=self.request.capacity_ah,
            notes=self.request.notes,
            profile=self.request.profile,
            stage="mix",
        )
        self._transition_state(ManualSessionState.COOLING, "manual_main_to_mix_prepare")
        self.cooling_started_at = time.time()
        await self._resume_after_cooling()

    def _mix_hold_reason(self, *, now: float) -> Optional[str]:
        if self.request is None or self.request.operation_mode != "mix":
            return None
        if self.finish_hold_started_at is None:
            return None
        hold_seconds = (
            self.request.profile.mix.hold_seconds
            if self.request.profile is not None
            else MANUAL_MIX_FINISH_HOLD_SEC
        )
        if now - float(self.finish_hold_started_at) >= hold_seconds:
            logger.info(
                "MANUAL_EVIDENCE kind=delta event=hold_complete mode=mix hold_seconds=%.1f timestamp=%.3f",
                hold_seconds,
                now,
            )
            return "manual_mix_delta_hold_complete"
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
        now = time.time()
        reason = self._threshold_reason(voltage, current)
        if reason is None:
            reason = self._main_tail_reason(live)
        if reason == "manual_main_to_mix":
            await self._advance_profile_to_mix()
            return
        if reason is None:
            reason = self._mix_hold_reason(now=now)
        if reason is None:
            reason = self._delta_reason(live, now=now)
            if reason == "manual_delta_confirmed":
                self.finish_hold_started_at = now
                self._persist()
                logger.info(
                    "MANUAL_EVIDENCE kind=delta event=hold_start mode=mix hold_seconds=%.1f timestamp=%.3f",
                    self.request.profile.mix.hold_seconds if self.request.profile is not None else MANUAL_MIX_FINISH_HOLD_SEC,
                    now,
                )
                reason = None
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
                self._transition_state(ManualSessionState.FAILED, self.stop_reason)
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
