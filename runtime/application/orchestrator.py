"""V3 runtime orchestration without domain ownership or physical execution."""

from __future__ import annotations

from typing import Any, Mapping

from runtime.journal import JournalEventFactory, JournalEventType, JournalSeverity

from .context import RuntimeContext
from .lifecycle import RuntimeLifecycle, RuntimeLifecycleState


class RuntimeOrchestrator:
    def __init__(self, context: RuntimeContext) -> None:
        self.context = context
        self.lifecycle = RuntimeLifecycle()
        self.last_snapshot: Any = None
        self.last_result: Mapping[str, Any] | None = None

    def start(self) -> None:
        self.lifecycle.start()

    def stop(self) -> None:
        self.lifecycle.stop()

    def tick(self, *, runtime_state: Any = None) -> Mapping[str, Any]:
        if self.lifecycle.state is not RuntimeLifecycleState.RUNNING:
            raise RuntimeError("orchestrator must be running")
        telemetry = self._read_telemetry()
        state = self._update_state(runtime_state, telemetry)
        diagnostics = self._evaluate_diagnostics(telemetry, state)
        charge = self._evaluate_charge(telemetry, state)
        intent = self._field(charge, "intent", charge)
        safety = self._evaluate_safety(intent, telemetry, state, diagnostics)
        execution = self._evaluate_execution(intent, safety)
        self._record("EXECUTION_DENIED" if not self._field(execution, "allowed", True) else "CHARGE_TICK", state, execution)
        self.last_snapshot = self._build_snapshot(state, telemetry, diagnostics, safety, execution)
        self.last_result = {"telemetry": telemetry, "state": state, "diagnostics": diagnostics, "charge": charge, "safety": safety, "execution": execution, "snapshot": self.last_snapshot}
        return self.last_result

    def process_command(self, command: Any, adapter: Any, *, context: Any = None) -> Any:
        result = adapter.adapt(command, context)
        event_type = JournalEventType.START if getattr(result, "intent", None) else JournalEventType.ERROR
        self._record("COMMAND_ACCEPTED" if getattr(result, "intent", None) else "COMMAND_REJECTED", "command", result, event_type=event_type)
        return result

    def build_snapshot(self) -> Any:
        return self.last_snapshot

    def _read_telemetry(self) -> Any:
        try:
            provider = self.context.telemetry_provider
            return provider() if callable(provider) else provider.read()
        except Exception as exc:
            self._record("TELEMETRY_UNAVAILABLE", "telemetry", {"error": str(exc)}, event_type=JournalEventType.TELEMETRY, severity=JournalSeverity.ERROR)
            return None

    def _update_state(self, runtime_state: Any, telemetry: Any) -> Any:
        provider = self.context.charge_service
        updater = getattr(provider, "update_state", None)
        return updater(runtime_state, telemetry) if updater else runtime_state

    def _evaluate_diagnostics(self, telemetry: Any, state: Any) -> Any:
        try:
            engine = self.context.diagnostics_engine
            return engine.evaluate(telemetry, state)
        except Exception as exc:
            self._record("DIAGNOSTICS_DEGRADED", "diagnostics", {"error": str(exc)}, event_type=JournalEventType.ERROR, severity=JournalSeverity.WARNING)
            return {"degraded": True, "error": str(exc)}

    def _evaluate_charge(self, telemetry: Any, state: Any) -> Any:
        try:
            return self.context.charge_service.evaluate(state, telemetry)
        except Exception as exc:
            self._record("STRATEGY_FAILURE", "charge", {"error": str(exc)}, event_type=JournalEventType.ERROR, severity=JournalSeverity.ERROR)
            return {"intent": None, "error": str(exc)}

    def _evaluate_safety(self, intent: Any, telemetry: Any, state: Any, diagnostics: Any) -> Any:
        try:
            engine = self.context.safety_engine
            return engine.evaluate(intent, telemetry, state, diagnostics)
        except Exception as exc:
            self._record("SAFETY_FAILURE", "safety", {"error": str(exc)}, event_type=JournalEventType.SAFETY, severity=JournalSeverity.ERROR)
            return {"allowed": False, "reason": "safety_evaluation_failed", "error": str(exc)}

    def _evaluate_execution(self, intent: Any, safety: Any) -> Any:
        try:
            return self.context.execution_policy.evaluate(intent, safety)
        except Exception as exc:
            return {"allowed": False, "reason": "execution_policy_failed", "error": str(exc)}

    def _build_snapshot(self, state: Any, telemetry: Any, diagnostics: Any, safety: Any, execution: Any) -> Any:
        builder = self.context.ui_snapshot_builder
        values = {"state": state, "telemetry": telemetry, "diagnostics": diagnostics, "safety": safety, "execution": execution}
        return builder(values) if callable(builder) else builder.build(values)

    def _record(self, message: str, stage: Any, details: Any, *, event_type=JournalEventType.TRANSITION, severity=JournalSeverity.INFO) -> None:
        entry = JournalEventFactory.event(0.0, event_type, str(stage or "runtime"), message, details={"value": details}, severity=severity)
        self.context.journal_recorder.append(entry)

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)
