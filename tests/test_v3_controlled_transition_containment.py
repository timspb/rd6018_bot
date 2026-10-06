import unittest

from runtime.output.bridge import (
    HardwareCapability,
    HardwareSnapshot,
    PhysicalBridgeExecutor,
    PhysicalExecutionConfig,
    PhysicalExecutionGate,
    PhysicalGateState,
)
from runtime.output.execution_policy import ExecutionPolicyDecision
from runtime.output.executor import build_command_plan
from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.physical.lease import BenchLeaseProvider, BenchLeaseScope


class _AsyncTransitionTransport:
    def __init__(self, *, delayed_on_once=False, never_confirm_on=False):
        self.delayed_on_once = delayed_on_once
        self.never_confirm_on = never_confirm_on
        self.output = False
        self.calls = []
        self.v = 13.57
        self.i = 0.10
        self.ovp = 14.07
        self.ocp = 0.20
        self._delayed_once = False

    async def read_snapshot(self):
        visible_output = self.output
        if self.output and self.never_confirm_on:
            visible_output = False
        elif self.output and self.delayed_on_once and not self._delayed_once:
            visible_output = False
            self._delayed_once = True
        return HardwareSnapshot(
            1, "connected", visible_output, 0.0, 0.0,
            self.v, self.i, self.ovp, self.ocp, 25.0, 13.07,
        )

    async def set_voltage(self, value):
        self.calls.append("set_voltage")
        self.v = float(value)

    async def set_current(self, value):
        self.calls.append("set_current")
        self.i = float(value)

    async def set_ovp(self, value):
        self.calls.append("set_ovp")
        self.ovp = float(value)

    async def set_ocp(self, value):
        self.calls.append("set_ocp")
        self.ocp = float(value)

    async def enable_output(self):
        self.calls.append("enable_output")
        self.output = True

    async def disable_output(self):
        self.calls.append("disable_output")
        self.output = False


def _capability():
    return HardwareCapability(
        True, True, 0.01, 18.0, 0.01, 0.01, 12.0, 0.01,
        True, True, False, True, True, True,
    )


class ControlledTransitionContainmentTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, transport):
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        gate.arm("operator")
        executor = PhysicalBridgeExecutor(gate, transport)
        provider = BenchLeaseProvider(duration_s=60)
        lease = provider.request("operator", BenchLeaseScope.CONTROLLED_STATE_TRANSITION)
        parameters = {
            "set_voltage": 13.57,
            "set_current": 0.10,
            "set_ovp": 14.07,
            "set_ocp": 0.20,
        }
        intent = SafeOutputIntent(OutputAction.ENABLE, 13.57, 0.10)
        plan = build_command_plan(intent, protection_ovp=14.07, protection_ocp=0.20)
        return executor, await executor.execute_controlled_transition(
            plan,
            ExecutionPolicyDecision(True, "ok"),
            lease,
            _capability(),
            lease_provider=provider,
            parameters=parameters,
            tolerances={
                "voltage_setpoint": 0.02,
                "current_setpoint": 0.02,
                "ovp": 0.02,
                "ocp": 0.02,
                "measured_current": 0.01,
            },
            readback_timeout_s=0.05,
            readback_poll_interval_s=0.01,
            on_hold_seconds=0.0,
            off_timeout_s=0.05,
            off_poll_interval_s=0.01,
        )

    async def test_success_finishes_off(self):
        transport = _AsyncTransitionTransport()
        executor, record = await self._run(transport)
        self.assertEqual(record.result, "EXECUTED")
        self.assertFalse(transport.output)
        self.assertEqual(transport.calls.count("disable_output"), 1)
        self.assertEqual(executor.gate.state, PhysicalGateState.READY)

    async def test_delayed_on_readback_is_polled_before_hold(self):
        transport = _AsyncTransitionTransport(delayed_on_once=True)
        executor, record = await self._run(transport)
        self.assertEqual(record.result, "EXECUTED")
        self.assertTrue(transport._delayed_once)
        self.assertFalse(transport.output)
        self.assertEqual(executor.gate.state, PhysicalGateState.READY)

    async def test_post_enable_failure_forces_verified_off_containment(self):
        transport = _AsyncTransitionTransport(never_confirm_on=True)
        gate = PhysicalExecutionGate(PhysicalExecutionConfig(enabled=True))
        gate.arm("operator")
        executor = PhysicalBridgeExecutor(gate, transport)
        provider = BenchLeaseProvider(duration_s=60)
        lease = provider.request("operator", BenchLeaseScope.CONTROLLED_STATE_TRANSITION)
        parameters = {"set_voltage": 13.57, "set_current": 0.10, "set_ovp": 14.07, "set_ocp": 0.20}
        plan = build_command_plan(
            SafeOutputIntent(OutputAction.ENABLE, 13.57, 0.10),
            protection_ovp=14.07,
            protection_ocp=0.20,
        )
        with self.assertRaisesRegex(Exception, "output ON was not confirmed"):
            await executor.execute_controlled_transition(
                plan,
                ExecutionPolicyDecision(True, "ok"),
                lease,
                _capability(),
                lease_provider=provider,
                parameters=parameters,
                tolerances={
                    "voltage_setpoint": 0.02,
                    "current_setpoint": 0.02,
                    "ovp": 0.02,
                    "ocp": 0.02,
                    "measured_current": 0.01,
                },
                readback_timeout_s=0.05,
                readback_poll_interval_s=0.01,
                off_timeout_s=0.05,
                off_poll_interval_s=0.01,
            )
        self.assertFalse(transport.output)
        self.assertIn("disable_output", transport.calls)
        self.assertEqual(executor.gate.state, PhysicalGateState.FAILED)
        failed = executor.audit.records[-1]
        self.assertIn("containment_disable_output", failed.actions)
        self.assertIn("containment_verify_off", failed.actions)


if __name__ == "__main__":
    unittest.main()
