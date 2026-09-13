import asyncio
import unittest

from runtime.output.bridge import HardwareCapability, PhysicalBridgeExecutor, PhysicalExecutionConfig, PhysicalExecutionGate
from runtime.output.executor import ExecutionLeaseState
from runtime.output.executor.command_plan import PhysicalCommandPlan, PhysicalCommandStep
from runtime.output.execution_policy import ExecutionPolicyDecision
from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.output.bridge import HardwareSnapshot


class _AsyncTransport:
    def __init__(self, after):
        self.after = after
        self.calls = []
        self.reads = 0

    async def disable_output(self):
        self.calls.append("disable_output")

    async def read_snapshot(self):
        self.reads += 1
        if self.reads == 1:
            return HardwareSnapshot(1, "connected", True, 13.9, 0.5)
        return self.after


def _capability():
    return HardwareCapability(False, True, .01, 18, .01, .01, 12, .01, False, False, False, True, True, True)


def _plan():
    return PhysicalCommandPlan(SafeOutputIntent(OutputAction.DISABLE, source="bench"),
                                (PhysicalCommandStep("disable_output"),))


class VerifiedOffExecutionTests(unittest.TestCase):
    def test_disable_is_verified_and_does_not_reset_or_enable(self):
        transport = _AsyncTransport(HardwareSnapshot(2, "connected", False, 0.0, 0.0))
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        gate.arm("operator")
        executor = PhysicalBridgeExecutor(gate, transport)
        record = asyncio.run(executor.execute_verified_disable(
            _plan(), ExecutionPolicyDecision(True, "ok"),
            ExecutionLeaseState("bench", 1, 1, "active"), _capability()))
        self.assertEqual(record.result, "EXECUTED")
        self.assertEqual(transport.calls, ["disable_output"])
        self.assertEqual(record.readback["after"].output_state, False)
        self.assertEqual(record.readback["after"].measured_current, 0.0)

    def test_nonzero_current_fails_closed(self):
        transport = _AsyncTransport(HardwareSnapshot(2, "connected", False, 0.0, 0.2))
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        gate.arm("operator")
        executor = PhysicalBridgeExecutor(gate, transport)
        with self.assertRaises(Exception):
            asyncio.run(executor.execute_verified_disable(
                _plan(), ExecutionPolicyDecision(True, "ok"),
                ExecutionLeaseState("bench", 1, 1, "active"), _capability()))
        self.assertEqual(transport.calls, ["disable_output"])
