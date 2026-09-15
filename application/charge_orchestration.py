"""Pure application orchestration between operator input and charge domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from runtime.charge import (
    BatteryProfile,
    ChargeEngine,
    DomainDecision,
    Measurements,
    ProfileRegistry,
    SessionManager,
    SessionSnapshot,
    StrategyRuntimeState,
)
from runtime.charge.strategy import ChargeStrategy

from .intents import OperatorIntent, OperatorIntentKind


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Application input; it contains values, never a provider/client."""

    voltage: Optional[float]
    current: Optional[float]
    temperature: Optional[float]
    output_on: Optional[bool]
    captured_at: datetime


@dataclass(frozen=True)
class ApplicationDecision:
    """Application result passed to a future outer adapter."""

    accepted: bool
    reason: str
    session: SessionSnapshot
    domain: DomainDecision | None = None


class ChargeApplicationService:
    """Coordinate intent, session and pure domain evaluation only."""

    def __init__(self, profiles: ProfileRegistry, sessions: SessionManager) -> None:
        self.profiles = profiles
        self.sessions = sessions
        self._engine: ChargeEngine | None = None
        self._strategy_state: StrategyRuntimeState | None = None

    def handle(self, intent: OperatorIntent, telemetry: TelemetrySnapshot) -> ApplicationDecision:
        if not isinstance(intent, OperatorIntent):
            return self._reject("invalid_operator_intent")
        if not isinstance(telemetry, TelemetrySnapshot):
            return self._reject("invalid_telemetry_snapshot")
        kind = intent.kind
        if kind is OperatorIntentKind.START_CHARGE:
            return self._start(intent, telemetry)
        if kind is OperatorIntentKind.STOP_CHARGE:
            return self._stop()
        if kind is OperatorIntentKind.PAUSE_CHARGE:
            return self._lifecycle(self.sessions.pause, "paused")
        if kind is OperatorIntentKind.RESUME_CHARGE:
            return self._lifecycle(self.sessions.resume, "resumed")
        if kind in {OperatorIntentKind.REFRESH_PANEL, OperatorIntentKind.REFRESH}:
            return self._evaluate(telemetry)
        return self._reject("unsupported_application_intent")

    def _start(self, intent: OperatorIntent, telemetry: TelemetrySnapshot) -> ApplicationDecision:
        profile_name = str(intent.parameters.get("profile", "")).strip()
        try:
            capacity = float(intent.parameters.get("capacity_ah", 0))
            battery: BatteryProfile = self.profiles.create_battery(profile_name, capacity)
            session = self.sessions.start(str(intent.parameters.get("session_id", intent.user)), profile_name)
        except (KeyError, TypeError, ValueError) as exc:
            return self._reject(f"start_rejected:{exc}")
        self._strategy_state = StrategyRuntimeState(stage="main")
        self._engine = ChargeEngine(battery, strategy=ChargeStrategy(battery, battery.recipe))
        return self._evaluate(telemetry, session=session)

    def _evaluate(self, telemetry: TelemetrySnapshot, *, session: SessionSnapshot | None = None) -> ApplicationDecision:
        session = session or self.sessions.snapshot
        if session.status.value != "active" or self._engine is None or self._strategy_state is None:
            return ApplicationDecision(False, "no_active_charge_session", session)
        measurements = Measurements(telemetry.voltage, telemetry.current, telemetry.temperature, telemetry.captured_at.timestamp())
        decision = self._engine.decision(self._strategy_state, measurements)
        return ApplicationDecision(True, "domain_evaluated", session, decision)

    def _stop(self) -> ApplicationDecision:
        session = self.sessions.stop()
        containment = ChargeEngine.containment_request("operator_stop", "operator stop request")
        return ApplicationDecision(True, "stopped", session, DomainDecision(session.status.value, None, containment, reason="operator_stop"))

    def _lifecycle(self, operation, reason: str) -> ApplicationDecision:
        try:
            session = operation()
        except ValueError as exc:
            return self._reject(f"lifecycle_rejected:{exc}")
        return ApplicationDecision(True, reason, session)

    def _reject(self, reason: str) -> ApplicationDecision:
        return ApplicationDecision(False, reason, self.sessions.snapshot)
