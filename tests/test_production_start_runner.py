import asyncio
import unittest
from types import SimpleNamespace
from pathlib import Path

from application.production_start_execution_port import (
    ProductionStartExecutionPort,
    ProductionStartMode,
)
from application.production_start_runner import ProductionStartRunner
from application.v2_start_runner_adapter import V2StartRunnerAdapter, build_v2_start_event_context
from application.v2_start_event_context import V2StartEventContext
from application.operator_feedback import (
    LegacyFeedbackStatus,
    build_legacy_feedback_bridge,
)
from application.start_execution_contract import request_from_trace
from application.start_activation_policy import StartActivationPolicy, StartExecutionMode
from application.start_plan import approved_plan_from_preflight
from application.start_preflight import StartPreflightService
from application.start_request import StartRequest
from application.v2_start_transaction_adapter import (
    RollbackState,
    StartExecutionStatus,
    V2StartTransactionAdapter,
    V2TransactionOutcome,
)
from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, ChargeIntent


class _Hass:
    async def get_all_live(self):
        return {
            "battery_voltage": 13.5, "current": 0.0, "temp_ext": 25.0,
            "temp_int": 30.0, "input_voltage": 60.0, "switch": "off",
            "ovp_triggered": "off", "ocp_triggered": "off",
            "_freshness": {key: 0.0 for key in (
                "battery_voltage", "current", "temp_ext", "temp_int",
                "switch", "ovp_triggered", "ocp_triggered",
            )},
        }


class _Controller:
    is_active = False

    def _main_target(self, _temperature):
        return 14.4, 7.0

    def _prep_target(self, _temperature):
        return 12.0, 0.7


class _App:
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1
    hass = _Hass()
    charge_controller = _Controller()
    rd_control_mode_manager = SimpleNamespace(hands_off=False)

    @staticmethod
    def _cap_current(value):
        return min(float(value), 12.0)


def _request():
    result = asyncio.run(StartPreflightService(_App()).evaluate(StartRequest(
        profile="AGM",
        capacity_ah=70,
        battery_identity=BatteryIdentity("runner-battery", BatteryChemistry.AGM, 70),
        operator="runner-test",
    )))
    plan = approved_plan_from_preflight(result)
    from application.runtime_start_service import RuntimeStartService
    trace = RuntimeStartService().build_trace(plan)
    return request_from_trace(plan, trace, trace_id="trace-runner")


def _active_policy():
    return StartActivationPolicy(
        execution_mode=StartExecutionMode.ACTIVE,
        explicit_active_enable=True,
        bench_validation_passed=True,
        rollback_validation_passed=True,
        physical_gate_passed=True,
    )


class ProductionStartRunnerTests(unittest.TestCase):
    def test_active_denied_without_gates_and_runner_not_called(self):
        calls = []
        runner = ProductionStartRunner(
            V2StartTransactionAdapter(), StartActivationPolicy(),
            lambda _input: calls.append("called"),
        )
        result = runner.execute(_request())
        self.assertEqual(result.status, StartExecutionStatus.DENIED)
        self.assertIn("explicit_active_enable_missing", result.reason)
        self.assertEqual(result.trace_id, "trace-runner")
        self.assertEqual(calls, [])

    def test_active_accepts_fake_runner_with_all_gates(self):
        calls = []

        def fake_runner(transaction_input):
            calls.append(transaction_input)
            return V2TransactionOutcome(trace_id=transaction_input.trace_id, started=True, reason="started")

        result = ProductionStartRunner(
            V2StartTransactionAdapter(), _active_policy(), fake_runner
        ).execute(_request())
        self.assertEqual(result.status, StartExecutionStatus.STARTED)
        self.assertEqual(result.trace_id, "trace-runner")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].trace_id, "trace-runner")

    def test_runner_normalizes_rollback_mapping(self):
        result = ProductionStartRunner(
            V2StartTransactionAdapter(), _active_policy(),
            lambda item: V2TransactionOutcome(
                trace_id=item.trace_id, contained=True,
                output_off_unconfirmed=True, session_contained=True,
                reason="off_unconfirmed",
            ),
        ).execute(_request())
        self.assertEqual(result.status, StartExecutionStatus.CONTAINED)
        self.assertEqual(result.rollback, RollbackState.SESSION_CONTAINED)
        self.assertEqual(result.trace_id, "trace-runner")

    def test_port_requires_runner_even_when_activation_gates_pass(self):
        request = _request()
        result = ProductionStartExecutionPort(
            activation_policy=_active_policy(),
        ).submit(request.plan, trace_id=request.trace_id, mode=ProductionStartMode.ACTIVE)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "active_runner_not_configured")

    def test_runner_has_no_direct_controller_dependency(self):
        source = Path("application/production_start_runner.py").read_text(encoding="utf-8")
        self.assertNotIn("ChargeController", source)
        self.assertNotIn("HassClient", source)
        self.assertNotIn("SafeOutputCoordinator", source)

    def test_async_v2_runner_adapter_calls_only_transaction_owner(self):
        calls = []

        async def fake_owner(app, event, pending):
            calls.append((app, event, pending))
            return True

        transaction = V2StartTransactionAdapter().prepare(
            _request().plan,
            trace_id="trace-owner",
        )
        adapter = V2StartRunnerAdapter(
            app="v2-app",
            event_factory=lambda item: ("event", item.trace_id),
            transaction_owner=fake_owner,
        )
        outcome = asyncio.run(adapter(transaction))
        self.assertTrue(outcome.started)
        self.assertEqual(outcome.trace_id, "trace-owner")
        self.assertEqual(calls[0][0], "v2-app")
        self.assertEqual(calls[0][1], ("event", "trace-owner"))
        self.assertEqual(calls[0][2].profile, "AGM")

    def test_event_context_contains_correlation_and_domain_metadata(self):
        transaction = V2StartTransactionAdapter().prepare(
            _request().plan,
            trace_id="trace-context",
            intent=ChargeIntent.NORMAL,
            condition=BatteryCondition.UNKNOWN,
            execution_metadata={"operator": "operator-7", "source": "telegram"},
        )
        context = build_v2_start_event_context(transaction)
        self.assertIsInstance(context, V2StartEventContext)
        self.assertEqual(context.trace_id, "trace-context")
        self.assertEqual(context.actor, "operator-7")
        self.assertEqual(context.source, "telegram")
        self.assertEqual(context.profile, "AGM")
        self.assertEqual(context.capacity_ah, 70.0)
        self.assertEqual(context.correlation_metadata["trace_id"], "trace-context")

    def test_default_event_context_is_data_only(self):
        transaction = V2StartTransactionAdapter().prepare(_request().plan, trace_id="trace-data")
        context = build_v2_start_event_context(transaction)
        self.assertFalse(hasattr(context, "controller"))
        self.assertFalse(hasattr(context, "hass"))
        self.assertEqual(context.trace_id, "trace-data")

    def test_default_adapter_propagates_context_to_v2_owner(self):
        received = []

        async def fake_owner(_app, event, pending):
            received.append((event, pending))
            return True

        transaction = V2StartTransactionAdapter().prepare(
            _request().plan,
            trace_id="trace-propagated",
            execution_metadata={"operator": "operator-9", "source": "telegram"},
        )
        outcome = asyncio.run(
            V2StartRunnerAdapter(app="v2-app", transaction_owner=fake_owner)(transaction)
        )
        self.assertTrue(outcome.started)
        self.assertEqual(outcome.trace_id, "trace-propagated")
        self.assertEqual(received[0][0].actor, "operator-9")
        self.assertEqual(received[0][0].source, "telegram")
        self.assertEqual(received[0][0].correlation_metadata["trace_id"], "trace-propagated")
        self.assertEqual(received[0][1].profile, "AGM")

    def test_feedback_bridge_propagates_trace_without_transport_in_context(self):
        published = []

        class FakeFeedbackPort:
            async def publish(self, **event):
                published.append(event)

        context = V2StartEventContext(
            trace_id="trace-feedback",
            actor="operator-11",
            source="telegram",
            profile="AGM",
            capacity_ah=70.0,
            condition=BatteryCondition.UNKNOWN,
            correlation_metadata={"trace_id": "trace-feedback"},
        )
        bridge = build_legacy_feedback_bridge(context, FakeFeedbackPort())
        asyncio.run(bridge.publish_status(LegacyFeedbackStatus.DENIED, "blocked"))
        self.assertEqual(published[0]["trace_id"], "trace-feedback")
        self.assertEqual(published[0]["status"], "DENIED")
        self.assertFalse(hasattr(context, "telegram"))
        self.assertFalse(hasattr(context, "controller"))


if __name__ == "__main__":
    unittest.main()
