"""Shadow mapping of existing actuator paths to :class:`ActuatorIntent`.

The inventory is descriptive only. Mapping never calls an actuator, controller,
FSM, safety guard, HA client, ESPHome client, or physical adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ActuatorTrigger,
    ExistingActuatorRequest,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
    map_existing_request,
)


@dataclass(frozen=True)
class ActuatorPathMapping:
    path_id: str
    current_operation: ActuatorOperation
    caller: str
    owner: str
    current_trigger: str
    reason: str
    target: Any
    classification: str
    trigger: ActuatorTrigger = ActuatorTrigger.MANUAL_ACTION
    rollback_policy: RollbackPolicy = RollbackPolicy.SAFE_OFF
    safety_context: SafetyContext = SafetyContext("observed", "unchanged", "none", "not_requested", "phase4")
    verification_expectation: PhysicalVerificationExpectation = PhysicalVerificationExpectation("unchanged", False, "none")

    def to_request(self) -> ExistingActuatorRequest:
        return ExistingActuatorRequest(
            source=self.caller,
            operation=self.current_operation,
            target=self.target,
            reason=self.reason,
            owner=self.owner,
            trigger=self.trigger,
            rollback_policy=self.rollback_policy,
            safety_context=self.safety_context,
            verification_expectation=self.verification_expectation,
        )

    def to_intent(
        self,
        *,
        trace_id: str,
    ) -> ActuatorIntent:
        return map_existing_request(
            self.to_request(),
            trace_id=trace_id,
        )


_PATHS = (
    ActuatorPathMapping("v2-runtime-output-on", ActuatorOperation.OUTPUT_ON, "runtime/v2_runtime.py", "V2 runtime safety surface", "program/manual/recovery action", "apply guarded output enable", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("manual-session-output-on", ActuatorOperation.OUTPUT_ON, "manual_mode.py:start", "Manual manager + SafeOutput path", "manual start", "start approved manual session", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("manual-resume-output-on", ActuatorOperation.OUTPUT_ON, "manual_mode.py:_resume_after_cooling", "Manual manager + SafeOutput path", "cooling recovery", "resume guarded manual session", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("v2-start-output-on", ActuatorOperation.OUTPUT_ON, "v2_startup.py:start_profile_transactional", "V2 transaction owner", "approved V2 START", "enable transaction target", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("v2-mix-output-on", ActuatorOperation.OUTPUT_ON, "v2_mix_mode.py:start_mix_transactional", "V2 transaction owner", "approved Mix transition", "enable Mix transaction", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("watchdog-output-off", ActuatorOperation.OUTPUT_OFF, "runtime/v2_runtime.py:_hard_stop_charge", "V2 watchdog + safety", "timeout/high voltage", "contain active output", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("manual-stop-output-off", ActuatorOperation.OUTPUT_OFF, "manual_mode.py:stop", "Manual manager + safety", "operator stop/session failure", "stop manual output", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("manual-runtime-containment-off", ActuatorOperation.OUTPUT_OFF, "manual_runtime_v2.py:_contain_enable_exception", "Manual runtime safety", "enable exception", "contain failed enable", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("safe-output-force-off", ActuatorOperation.OUTPUT_OFF, "safe_output.py:_force_off", "SafeOutputCoordinator", "transaction failure", "force verified OFF", "RD6018 Output", "KEEP"),
    ActuatorPathMapping("runtime-set-voltage", ActuatorOperation.SET_VOLTAGE, "runtime/v2_runtime.py action executor", "V2 runtime safety surface", "controller action", "apply guarded voltage target", "RD6018 voltage setpoint", "KEEP"),
    ActuatorPathMapping("diagnostic-set-voltage", ActuatorOperation.SET_VOLTAGE, "diagnostic_probe.py", "diagnostic safety boundary", "controlled probe", "apply temporary diagnostic voltage", "RD6018 voltage setpoint", "DEPRECATE"),
    ActuatorPathMapping("runtime-set-current", ActuatorOperation.SET_CURRENT, "runtime/v2_runtime.py action executor", "V2 runtime safety surface", "controller action", "apply guarded current target", "RD6018 current setpoint", "KEEP"),
    ActuatorPathMapping("diagnostic-set-current", ActuatorOperation.SET_CURRENT, "diagnostic_probe.py", "diagnostic safety boundary", "controlled probe", "apply temporary diagnostic current", "RD6018 current setpoint", "DEPRECATE"),
)


def known_actuator_paths() -> tuple[ActuatorPathMapping, ...]:
    return _PATHS


def observe_actuator_path(path_id: str, *, trace_id: str) -> ActuatorIntent:
    for path in _PATHS:
        if path.path_id == path_id:
            return path.to_intent(trace_id=trace_id)
    raise KeyError(f"unknown actuator path: {path_id}")
