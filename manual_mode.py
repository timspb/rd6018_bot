from __future__ import annotations

import asyncio
import logging
import math
import time
from pathlib import Path
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional

from runtime.safety.variables import MAX_STAGE_CURRENT_A

MAX_STAGE_CURRENT = float(MAX_STAGE_CURRENT_A.default)
from config import MAX_MANUAL_VOLTAGE
from runtime.charge.profiles.manual import ManualChargeProfile, load_manual_profile
from runtime.charge.manual_session_store import (
    read_manual_session_document,
    write_manual_session_document,
)
from runtime.charge.programs.manual import manual_stop_threshold_reason
from runtime.charge.evidence.first_stage_variables import (
    MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A as MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC,
)
from application.manual_identity_integration import ManualIdentityIntegrationAdapter
from application.manual_execution_boundary import ManualExecutionBoundary
from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.execution_port import get_or_create_execution_port
from runtime.charge.strategy.manual_phase_lifecycle import ManualPhaseLifecycle
from application.manual_phase_evidence import (
    evaluate_manual_main_tail,
    evaluate_manual_mix_hold,
)
from application.manual_start_use_case import start_manual_session
from application.manual_stop_use_case import stop_manual_session
from application.manual_cooling_use_case import (
    enter_manual_cooling,
    resume_manual_after_cooling,
)
from application.manual_mix_transition_use_case import advance_manual_profile_to_mix
from application.manual_supervisor_use_case import supervise_manual_session
from application.manual_observer_use_case import (
    MANUAL_COOLING_PAUSE_C,
    MANUAL_COOLING_RESUME_C,
    MANUAL_MIX_FINISH_HOLD_SEC,
    MANUAL_TEMP_CRITICAL_C,
    observe_manual_session_once,
)
from runtime.charge.evidence.manual_delta import (
    MANUAL_DELTA_BLANKING_SEC,
    MANUAL_DELTA_CONFIRM_COUNT,
    MANUAL_DELTA_CONFIRM_INTERVAL_SEC,
    ManualDeltaEvidencePolicy,
    ManualDeltaEvidenceState,
    ManualDeltaSample,
    evaluate_manual_delta_evidence,
)
from v3_core.canonical_events import EventType


MANUAL_SESSION_FILE = "manual_session_v2.json"
MANUAL_POLL_SEC = 5.0
MANUAL_MIX_VOLTAGE_THRESHOLD_V = 15.8
MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A = float(MANUAL_DEFAULT_MAIN_TAIL_CURRENT_SPEC.default)

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
    def operation_mode(self) -> str:
        return self.stage if self.profile is not None else ("mix" if float(self.voltage_v) >= MANUAL_MIX_VOLTAGE_THRESHOLD_V else "main")

    @property
    def operation_mode_label(self) -> str:
        return "Ручной МИКС" if self.operation_mode == "mix" else "Ручной Основной"


@dataclass(frozen=True)
class ManualUIIntent:
    """Validated operator intent produced by the Manual UI wizard."""

    user_id: int
    chat_id: int
    voltage_v: float
    current_a: float
    delta: float
    time_limit_hours: float
    capacity_ah: float

    def __post_init__(self) -> None:
        values = (self.voltage_v, self.current_a, self.delta, self.time_limit_hours, self.capacity_ah)
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("Manual UI values must be finite")
        if not 12.0 <= float(self.voltage_v) <= 17.0:
            raise ValueError("Manual UI voltage must be between 12 and 17 V")
        if not 0.1 <= float(self.current_a) <= MAX_STAGE_CURRENT:
            raise ValueError("Manual UI current is outside the safety envelope")
        if not 0.005 <= float(self.delta) <= 0.1:
            raise ValueError("Manual UI delta is outside the supported range")
        if not 0.0 < float(self.time_limit_hours) <= 72.0:
            raise ValueError("Manual UI time limit must be between 0 and 72 hours")
        if not 10.0 <= float(self.capacity_ah) <= 300.0:
            raise ValueError("Manual UI capacity must be between 10 and 300 Ah")

    @classmethod
    def from_dialog(cls, *, user_id: int, chat_id: int, params: dict[str, float]) -> "ManualUIIntent":
        return cls(
            user_id=int(user_id), chat_id=int(chat_id),
            voltage_v=float(params["main_voltage"]), current_a=float(params["main_current"]),
            delta=float(params["delta"]), time_limit_hours=float(params["time_limit"]),
            capacity_ah=float(params["capacity"]),
        )

    def to_request(self) -> ManualChargeRequest:
        return ManualChargeRequest(
            voltage_v=self.voltage_v, current_a=self.current_a,
            stop=ManualStopConditions(
                max_active_seconds=self.time_limit_hours * 3600.0, delta=self.delta,
            ),
            capacity_ah=self.capacity_ah, notes="Manual UI request",
        )


class ManualSessionManager:
    """Explicit manual authority: operator rules + non-bypassable hard safety.

    No Pb chemistry transition is executed here.  A configured timer/delta/threshold is
    an operator stop condition, not an automatic recipe decision.
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
        self.phase_transition_reason = ""
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
        self.identity_integration = ManualIdentityIntegrationAdapter()
        self.phase_lifecycle = ManualPhaseLifecycle()
        # Construction must remain compatible with persistence-only restore
        # callers that provide no live app/Hass object. Actual execution still
        # fails closed when the V2 owner is unavailable.
        self.execution_port = get_or_create_execution_port(self.app)
        self.execution_boundary = ManualExecutionBoundary(self.execution_port)
        self.identity_restore_resolution = "AMBIGUOUS"
        self._manual_start_event_emitted = False
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
            if self.identity_integration.identity is not None and self._manual_start_event_emitted:
                self.identity_integration.emit(
                    event_type=EventType.PHASE_TRANSITION,
                    phase_before=old_state.value,
                    phase_after=new_state.value,
                    reason=reason,
                )

    @property
    def is_active(self) -> bool:
        return self.state in {
            ManualSessionState.ARMING,
            ManualSessionState.ACTIVE,
            ManualSessionState.COOLING,
        }

    @property
    def session_identity(self):
        """Read-only identity view for diagnostics/evidence consumers."""
        return self.identity_integration.identity

    @property
    def canonical_events(self):
        """In-memory canonical events; no writer or transport is invoked."""
        return self.identity_integration.events

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
            "phase_transition_reason": self.phase_transition_reason,
            "finish_hold_started_at": self.finish_hold_started_at,
            "saved_at": time.time(),
            "session_identity": self.identity_integration.identity_payload(),
        }

    def _persist(self) -> None:
        try:
            write_manual_session_document(self.session_file, self._document())
        except OSError:
            logger.warning("Unable to persist Manual session document %s", self.session_file, exc_info=True)

    def _restore_as_interrupted(
        self,
        *,
        raw_document: dict[str, Any] | None = None,
        document_loaded: bool = False,
    ) -> None:
        raw = raw_document if document_loaded else read_manual_session_document(self.session_file)
        if raw is None:
            return
        request_raw = raw.get("request")
        try:
            restore_decision = self.identity_integration.restore(raw.get("session_identity"), now=time.time())
            self.identity_restore_resolution = restore_decision.resolution.value
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Unable to restore Manual session identity: %s", exc)
        if isinstance(request_raw, dict):
            stop_raw = request_raw.get("stop") or {}
            try:
                profile = None
                if isinstance(request_raw.get("profile"), dict):
                    profile = load_manual_profile(
                        Path(__file__).resolve().parent / "config" / "charge" / "manual.yaml",
                        battery_id=str(request_raw.get("battery_id") or "") or None,
                    )
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
        return await start_manual_session(
            self, request, max_manual_voltage=MAX_MANUAL_VOLTAGE
        )

    async def stop(self, reason: str = "operator_stop") -> bool:
        return await stop_manual_session(self, reason)

    async def _enter_cooling(self) -> None:
        return await enter_manual_cooling(self)

    async def _resume_after_cooling(self) -> None:
        return await resume_manual_after_cooling(
            self, max_manual_voltage=MAX_MANUAL_VOLTAGE
        )

    def _threshold_reason(self, voltage: float, current: float) -> Optional[str]:
        assert self.request is not None
        return manual_stop_threshold_reason(
            self.request.stop,
            active_elapsed_s=self.active_elapsed_s,
            voltage=voltage,
            current=current,
        )

    def _delta_reason(self, sample: ManualDeltaSample, *, now: float) -> Optional[str]:
        assert self.request is not None
        if self.request.operation_mode != "mix":
            return None

        profile = self.request.profile
        if profile is None:
            delta_current_a = self.request.stop.delta
            delta_voltage_v = self.request.stop.delta
            confirmation_count = MANUAL_DELTA_CONFIRM_COUNT
            confirmation_interval_seconds = MANUAL_DELTA_CONFIRM_INTERVAL_SEC
        else:
            delta_current_a = profile.mix.delta_current_a
            delta_voltage_v = profile.mix.delta_voltage_v
            confirmation_count = profile.mix.confirmation_count
            confirmation_interval_seconds = profile.mix.confirmation_interval_seconds

        state = ManualDeltaEvidenceState(
            imin=self._imin,
            vmax=self._vmax,
            confirmations=self._delta_confirmations,
            last_confirmation_at=self._last_delta_confirmation,
        )
        policy = ManualDeltaEvidencePolicy(
            delta_current_a=delta_current_a,
            delta_voltage_v=delta_voltage_v,
            confirmation_count=confirmation_count,
            confirmation_interval_seconds=confirmation_interval_seconds,
            blanking_seconds=MANUAL_DELTA_BLANKING_SEC,
        )
        result = evaluate_manual_delta_evidence(
            state,
            policy,
            sample,
            started_at=self.started_at,
            now=now,
        )
        self._imin = result.state.imin
        self._vmax = result.state.vmax
        self._delta_confirmations = result.state.confirmations
        self._last_delta_confirmation = result.state.last_confirmation_at
        return result.reason

    def _main_tail_reason(self, live: dict[str, Any]) -> Optional[str]:
        return evaluate_manual_main_tail(self, live)

    async def _advance_profile_to_mix(self) -> None:
        return await advance_manual_profile_to_mix(self)

    def _mix_hold_reason(self, *, now: float) -> Optional[str]:
        return evaluate_manual_mix_hold(self, now=now)

    async def observe_once(self) -> None:
        await observe_manual_session_once(self)

    async def _run(self) -> None:
        return await supervise_manual_session(self, poll_seconds=MANUAL_POLL_SEC)
