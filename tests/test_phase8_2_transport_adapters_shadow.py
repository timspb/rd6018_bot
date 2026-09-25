"""Phase 8.2 shadow transport adapter tests."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
import unittest

from application.actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ActuatorTrigger,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
)
from application.execution_boundary import ExecutionRequest
from application.transport_adapters_shadow import ESPDirectExecutionAdapter, HAExecutionAdapter
from application.containment_result import ContainmentVerificationState


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "application" / "transport_adapters_shadow.py"


def _request(operation: str) -> ExecutionRequest:
    intent = ActuatorIntent.new(
        trace_id="trace-shadow",
        source="v2-runtime",
        requested_operation=ActuatorOperation.OUTPUT_OFF,
        target=None,
        reason="shadow test",
        owner="V2 transaction owner",
        trigger=ActuatorTrigger.STOP_REQUEST,
        rollback_policy=RollbackPolicy.SAFE_OFF,
        safety_context=SafetyContext("fresh", "armed", "normal", "known", "limits-v1"),
        verification_expectation=PhysicalVerificationExpectation("off", True, "timeout"),
    )
    return ExecutionRequest(
        intent=intent,
        containment=None,
        owner=intent.owner,
        trigger=intent.trigger.value,
        safety_context=intent.safety_context,
        rollback_policy=intent.rollback_policy,
        verification_expectation=intent.verification_expectation,
        trace_id=intent.trace_id,
        correlation={"operation": operation},
    )


class ShadowTransportAdapterTests(unittest.TestCase):
    def test_ha_contract_compliance(self) -> None:
        adapter = HAExecutionAdapter()
        result = adapter.dispatch(_request("read_telemetry"))
        self.assertTrue(result.accepted)
        self.assertTrue(result.deferred)
        self.assertEqual("ha-shadow:read_telemetry:shadow_deferred", result.reason)
        telemetry = asyncio.run(adapter.read_telemetry())
        self.assertIsNone(telemetry.voltage)

    def test_esp_contract_compliance(self) -> None:
        adapter = ESPDirectExecutionAdapter()
        result = adapter.dispatch(_request("output_off"))
        self.assertTrue(result.accepted)
        self.assertTrue(result.deferred)
        self.assertEqual("esp-direct-shadow:output_off:shadow_deferred", result.reason)
        self.assertIsNone(asyncio.run(adapter.read_output_state()))

    def test_request_parity_between_adapters(self) -> None:
        ha = HAExecutionAdapter().dispatch(_request("set_voltage"))
        esp = ESPDirectExecutionAdapter().dispatch(_request("set_voltage"))
        self.assertEqual((ha.accepted, ha.rejected, ha.deferred, ha.verification_state), (esp.accepted, esp.rejected, esp.deferred, esp.verification_state))
        self.assertEqual(ha.request.trace_id, esp.request.trace_id)

    def test_all_shadow_operations_are_deferred(self) -> None:
        for operation in ("read_telemetry", "read_output_state", "read_readback", "set_voltage", "set_current", "output_on", "output_off"):
            result = HAExecutionAdapter().dispatch(_request(operation))
            self.assertTrue(result.accepted, operation)
            self.assertTrue(result.deferred, operation)
            self.assertEqual(ContainmentVerificationState.NOT_REQUESTED, result.verification_state)

    def test_no_domain_or_transport_client_imports(self) -> None:
        tree = ast.parse(ADAPTER.read_text(encoding="utf-8"), filename=str(ADAPTER))
        forbidden = ("runtime.charge", "charge_logic", "hass_api", "homeassistant", "esphome", "runtime.physical", "runtime.output", "telegram", "database", "persistence")
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertEqual([], [name for name in imports if any(token in name.lower() for token in forbidden)])
        physical_calls = [
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get_all_live", "turn_on", "turn_off", "set_voltage", "set_current"}
        ]
        self.assertEqual([], physical_calls)

    def test_document_tracks_shadow_only_boundary(self) -> None:
        text = (ROOT / "docs" / "RD6018_TRANSPORT_ADAPTER_MODEL.md").read_text(encoding="utf-8")
        for term in ("HAExecutionAdapter", "ESPDirectExecutionAdapter", "ExecutionRequest", "deferred=True", "physical execution"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
