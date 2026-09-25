import unittest

from runtime.output.bridge import (
    HardwareCapability, PhysicalBridgeExecutor, PhysicalExecutionConfig,
    PhysicalExecutionError, PhysicalExecutionGate, PhysicalGateState,
)
from runtime.output.executor import ExecutionLeaseState, build_command_plan
from runtime.output.execution_policy import ExecutionPolicyDecision
from runtime.output.intent import OutputAction, SafeOutputIntent


class _Transport:
    def __init__(self, output_state=False):
        self.actions = []
        self.output_state = output_state

    def apply(self, action, **values):
        self.actions.append(action)
        if action == "enable":
            self.output_state = True
        elif action == "disable":
            self.output_state = False

    def readback(self):
        return {"output_state": self.output_state}


def _capability():
    return HardwareCapability(True, True, 10, 18, .01, .1, 12, .01, True, True, True, True, True, True)


class PhysicalExecutionGateTests(unittest.TestCase):
    def test_disabled_by_default_rejects_without_transport_call(self):
        transport = _Transport()
        executor = PhysicalBridgeExecutor(PhysicalExecutionGate(), transport)
        plan = build_command_plan(SafeOutputIntent(OutputAction.DISABLE))
        with self.assertRaises(PhysicalExecutionError):
            executor.execute(plan, ExecutionPolicyDecision(True, "ok"), ExecutionLeaseState("bench", 1, 1, "active"), _capability())
        self.assertEqual(transport.actions, [])
        self.assertEqual(executor.gate.state, PhysicalGateState.DISABLED)

    def test_manual_armed_enable_has_readback_and_audit(self):
        transport = _Transport()
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        gate.arm("operator")
        audit = PhysicalBridgeExecutor(gate, transport)
        intent = SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0)
        record = audit.execute(build_command_plan(intent, protection_ovp=14.45, protection_ocp=2.05), ExecutionPolicyDecision(True, "ok"), ExecutionLeaseState("bench", 1, 1, "active"), _capability())
        self.assertEqual(record.result, "EXECUTED")
        self.assertEqual(transport.actions[-1], "enable")
        self.assertEqual(record.readback["output_state"], True)
        self.assertGreaterEqual(len(audit.audit.records), 2)

    def test_disable_verifies_off_before_reset(self):
        transport = _Transport(True)
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        gate.arm("operator")
        executor = PhysicalBridgeExecutor(gate, transport)
        executor.execute(build_command_plan(SafeOutputIntent(OutputAction.DISABLE)), ExecutionPolicyDecision(True, "ok"), ExecutionLeaseState("bench", 1, 1, "active"), _capability())
        self.assertLess(transport.actions.index("disable"), transport.actions.index("reset_protection"))
        self.assertFalse(transport.output_state)

    def test_missing_manual_arm_is_rejected(self):
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        with self.assertRaises(PhysicalExecutionError):
            gate.arm("")
