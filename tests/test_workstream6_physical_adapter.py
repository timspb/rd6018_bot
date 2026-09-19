import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from v3_core.bench_transport import BenchScenario, BenchTransport
from v3_core.configuration import minimal_v3_authority
from v3_core.contracts import ActuatorIntent, ActuatorOperation
from v3_core.physical_adapter import (
    AdapterVerificationStatus,
    ContainmentRequest,
    PhysicalAdapterConfig,
    V3PhysicalAdapter,
)
from v3_core.execution import ExecutionDispatcher


ROOT = Path(__file__).resolve().parents[1]


def intent(operation, target=None, trace="w6"):
    return ActuatorIntent(operation, target, "bench-test", trace)


class Workstream6PhysicalAdapterTests(unittest.TestCase):
    def adapter(self, scenario):
        now = datetime.now(timezone.utc)
        transport = BenchTransport(scenario, now=now)
        config = PhysicalAdapterConfig.from_authority(minimal_v3_authority())
        return V3PhysicalAdapter(transport, config, clock=lambda: now)

    def test_normal_operations_are_translated_and_verified(self):
        adapter = self.adapter(BenchScenario.SUCCESS)
        for operation, target in ((ActuatorOperation.OUTPUT_ON, None), (ActuatorOperation.OUTPUT_OFF, None), (ActuatorOperation.SET_VOLTAGE, 14.7), (ActuatorOperation.SET_CURRENT, 2.0)):
            result = adapter.execute(intent(operation, target))
            self.assertEqual(AdapterVerificationStatus.VERIFIED, result.verification_status)
            self.assertFalse(result.rollback_required)

    def test_dispatcher_to_v3_adapter_path_is_bench_only(self):
        adapter = self.adapter(BenchScenario.SUCCESS)
        result = ExecutionDispatcher(adapter).dispatch(intent(ActuatorOperation.OUTPUT_OFF))
        self.assertTrue(result.accepted)
        self.assertFalse(result.executed)
        self.assertEqual("OUTPUT_OFF", adapter.transport.commands[0][0])

    def test_failed_transport_and_rejection_are_explicit(self):
        for scenario, status in ((BenchScenario.TIMEOUT, AdapterVerificationStatus.TIMEOUT), (BenchScenario.UNAVAILABLE, AdapterVerificationStatus.FAILED), (BenchScenario.REJECTED, AdapterVerificationStatus.FAILED)):
            result = self.adapter(scenario).execute(intent(ActuatorOperation.OUTPUT_OFF))
            self.assertEqual(status, result.verification_status)
            self.assertTrue(result.rollback_required)

    def test_mismatch_and_stale_readback_are_not_success(self):
        wrong = self.adapter(BenchScenario.WRONG_READBACK).execute(intent(ActuatorOperation.SET_VOLTAGE, 14.7))
        stale = self.adapter(BenchScenario.STALE_STATE).execute(intent(ActuatorOperation.OUTPUT_OFF))
        self.assertEqual(AdapterVerificationStatus.FAILED, wrong.verification_status)
        self.assertEqual(AdapterVerificationStatus.STALE, stale.verification_status)

    def test_containment_and_rollback_are_intents_only(self):
        adapter = self.adapter(BenchScenario.SUCCESS)
        containment = adapter.containment(ContainmentRequest("trace-c", "emergency containment"))
        rollback = adapter.rollback(intent(ActuatorOperation.SET_CURRENT, 2.0, "trace-r"))
        self.assertEqual(ActuatorOperation.CONTAINMENT, containment.operation)
        self.assertEqual(ActuatorOperation.OUTPUT_OFF, rollback.operation)
        self.assertEqual([], adapter.transport.commands)

    def test_duplicate_owner_is_rejected(self):
        adapter = self.adapter(BenchScenario.SUCCESS)
        with self.assertRaises(ValueError):
            adapter.execute(ActuatorIntent(ActuatorOperation.OUTPUT_ON, None, "bad", "trace-owner", "V2 owner"))

    def test_adapter_has_no_direct_physical_import_or_call(self):
        for name in ("physical_adapter.py", "bench_transport.py"):
            path = ROOT / "v3_core" / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertTrue(all(not any(token in item for token in ("hass", "esphome", "runtime", "serial", "gpio")) for item in imports))
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("turn_on(", text)
            self.assertNotIn("turn_off(", text)

    def test_configuration_is_required_for_adapter_parameters(self):
        authority = minimal_v3_authority()
        with self.assertRaises(ValueError):
            PhysicalAdapterConfig.from_authority(authority, {"execution.command_timeout_s": 0.0})


if __name__ == "__main__":
    unittest.main()
