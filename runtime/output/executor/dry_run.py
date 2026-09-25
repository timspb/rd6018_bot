"""Non-actuating executor used for contract and sequence tests."""

from __future__ import annotations

from runtime.output.execution_policy import ExecutionPolicy, ExecutionPolicyContext, ExecutionPolicyDecision
from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.safety.engine import SafetyDecision

from .contract import PhysicalExecutor
from .records import ExecutionRecord


class DryRunExecutor(PhysicalExecutor):
    def __init__(self, safety: SafetyDecision, context: ExecutionPolicyContext = ExecutionPolicyContext()):
        self._safety = safety
        self._context = context
        self._policy = ExecutionPolicy()
        self.records: list[ExecutionRecord] = []

    def prepare(self, intent: SafeOutputIntent) -> ExecutionPolicyDecision:
        return self._policy.evaluate(intent, self._safety, self._context)

    def validate(self, intent: SafeOutputIntent) -> ExecutionPolicyDecision:
        return self.prepare(intent)

    def execute(self, intent: SafeOutputIntent) -> ExecutionRecord:
        validation = self.validate(intent)
        if not validation.allowed:
            record = ExecutionRecord(0.0, intent, validation, errors=validation.violations)
            self.records.append(record)
            return record
        if intent.action is OutputAction.ENABLE:
            actions = ("prepare", "set_voltage", "set_current", "set_ovp", "set_ocp", "readback", "enable")
        elif intent.action is OutputAction.DISABLE:
            actions = ("disable", "read_output_state", "confirm_off", "reset_protection")
        elif intent.action is OutputAction.RESET_PROTECTION:
            actions = ("reset_ovp", "reset_ocp", "readback")
        else:
            actions = (intent.action.value,)
        record = ExecutionRecord(0.0, intent, validation, actions, {"verified": False, "simulated": True})
        self.records.append(record)
        return record

    def verify(self, intent: SafeOutputIntent) -> ExecutionRecord:
        return self.execute(intent)

    def rollback(self, intent: SafeOutputIntent) -> ExecutionRecord:
        disable = SafeOutputIntent(OutputAction.DISABLE, source="dry_run:rollback")
        return self.execute(disable)
