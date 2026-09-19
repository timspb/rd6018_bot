"""WORKSTREAM 62: synthetic, non-production V3 end-to-end dry run.

This module deliberately uses only domain contracts and a recording mock.  The
mock stops at PhysicalExecutionRequest; it never calls a transport or target.
"""

import unittest

from application.charge_engine import BatteryState, GenericChargeEngine, TelemetrySnapshot
from application.charge_engine.models import Phase
from application.charge_engine.phases import PhaseLifecycleRegistry, canonical_phase_contracts
from application.charge_lifecycle import LifecycleRestoreClassifier, RestoreKind
from application.charge_program import (
    BatteryProfile,
    Chemistry,
    ManualProgramInput,
    Mode,
    ChargeProgramResolver,
)
from application.execution_intent import (
    DecisionIntentMapper,
    ExecutionIntent,
    ExecutionSafetyPolicy,
    SafetyContext as IntentSafetyContext,
    SafetyOutcome,
)
from application.physical_boundary import PhysicalExecutionBoundary, PhysicalExecutionRequest
from application.safety import SafetyContext, SafetyPolicy, SafetyState


class RecordingMockPhysicalBoundary:
    """A mock physical boundary that records requests and performs no I/O."""

    def __init__(self) -> None:
        self.requests = []

    def accept(self, request):
        if not isinstance(request, PhysicalExecutionRequest):
            raise TypeError("mock accepts only PhysicalExecutionRequest")
        self.requests.append(request)
        return request


def battery(battery_id: str, chemistry: Chemistry) -> BatteryProfile:
    return BatteryProfile(battery_id, chemistry, 60.0, manufacturer="synthetic", model="bench")


def manual_input() -> ManualProgramInput:
    return ManualProgramInput(
        main_voltage_v=14.4,
        main_current_a=6.0,
        mix_voltage_v=16.0,
        mix_current_a=1.8,
        delta_voltage_v=0.2,
        delta_current_a=0.3,
        hold_hours=2.0,
        max_mix_hours=20.0,
    )


class V3EndToEndDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ChargeProgramResolver()
        self.engine = GenericChargeEngine()
        self.lifecycle = PhaseLifecycleRegistry(canonical_phase_contracts())
        self.mock_boundary = RecordingMockPhysicalBoundary()

    def resolve_all_programs(self):
        programs = [
            self.resolver.resolve(battery("calcium-test", Chemistry.CALCIUM), Mode.AUTO),
            self.resolver.resolve(battery("efb-test", Chemistry.EFB), Mode.AUTO),
            self.resolver.resolve(battery("agm-test", Chemistry.AGM), Mode.AUTO),
            self.resolver.resolve(battery("Baic72", Chemistry.CALCIUM), Mode.MANUAL, manual_input()),
        ]
        return programs

    def evaluate_and_request(self, program, state, telemetry, *, timestamp=1.0):
        decision = self.engine.evaluate(program, state, telemetry)
        domain_safety = SafetyPolicy(16.5, 12.0, 45.0).evaluate(
            SafetyContext(
                voltage_v=telemetry.voltage_v,
                current_a=telemetry.current_a,
                temperatures_c=(telemetry.temperature_c,),
                protection_codes=(),
                telemetry_fresh=telemetry.fresh,
                telemetry_present=telemetry.voltage_v is not None and telemetry.current_a is not None,
                timestamp=telemetry.timestamp,
            )
        )
        if domain_safety.state is not SafetyState.ALLOW:
            return decision, domain_safety, None
        intent_context = IntentSafetyContext(
            telemetry_state="FRESH",
            lease_state="OBSERVE",
            containment_state="NORMAL",
            verification_state="PENDING",
            limits_reference="synthetic-safety",
        )
        intent_result = DecisionIntentMapper.from_decision(
            decision,
            intent_context,
            ExecutionSafetyPolicy(max_voltage_v=16.5, max_current_a=12.0),
        )
        if intent_result.outcome not in {SafetyOutcome.ALLOWED, SafetyOutcome.LIMITED}:
            return decision, domain_safety, None
        request = PhysicalExecutionBoundary().request(
            intent_result.intent, domain_safety, timestamp=timestamp
        )
        return decision, domain_safety, self.mock_boundary.accept(request)

    def test_all_programs_resolve_to_deterministic_domain_programs(self):
        for program in self.resolve_all_programs():
            first = self.resolver.resolve(
                program.battery_profile,
                program.mode,
                manual_input() if program.mode is Mode.MANUAL else None,
            )
            self.assertEqual(program, first)
            self.assertTrue(program.program_id)
            self.assertGreaterEqual(len(program.phases), 2)

    def test_full_flow_reaches_mock_request_without_side_effects(self):
        program = self.resolver.resolve(battery("calcium-test", Chemistry.CALCIUM), Mode.AUTO)
        telemetry = TelemetrySnapshot(1.0, 14.2, 6.0, 25.0)

        prep, _, no_request = self.evaluate_and_request(
            program, BatteryState(phase=Phase.PREP), telemetry
        )
        self.assertEqual(prep.next_phase, Phase.MAIN)
        self.assertIsNone(no_request)

        main, safety, request = self.evaluate_and_request(
            program, BatteryState(phase=Phase.MAIN), telemetry
        )
        self.assertEqual(safety.state, SafetyState.ALLOW)
        self.assertEqual(main.current_phase, Phase.MAIN)
        self.assertIsInstance(request, PhysicalExecutionRequest)
        self.assertEqual(len(self.mock_boundary.requests), 1)

    def test_phase_lifecycle_contract_covers_requested_flow(self):
        expected = ("PREP", "MAIN", "DESULFATION", "MIX", "HOLD", "SAFE_WAIT", "DONE")
        self.assertEqual(self.lifecycle.ids(), expected)
        mix = self.lifecycle.get("MIX")
        hold = self.lifecycle.get("HOLD")
        self.assertIsNotNone(mix.delta_policy)
        self.assertIsNotNone(hold.hold_policy)

    def test_synthetic_transition_sequence_is_deterministic(self):
        program = self.resolver.resolve(battery("efb-test", Chemistry.EFB), Mode.AUTO)
        telemetry = TelemetrySnapshot(2.0, 14.4, 5.0, 24.0)
        states = (
            BatteryState(phase=Phase.PREP),
            BatteryState(phase=Phase.MAIN, main_complete=True),
            BatteryState(phase=Phase.MIX, delta_confirmed=True),
            BatteryState(phase=Phase.HOLD, hold_complete=True),
            BatteryState(phase=Phase.SAFE_WAIT, safe_wait_complete=True),
        )
        decisions = [self.engine.evaluate(program, state, telemetry) for state in states]
        self.assertEqual([d.next_phase for d in decisions], [Phase.MAIN, Phase.MIX, Phase.HOLD, Phase.SAFE_WAIT, Phase.DONE])
        self.assertEqual(decisions, [self.engine.evaluate(program, state, telemetry) for state in states])

    def test_stale_and_missing_telemetry_fail_closed(self):
        program = self.resolver.resolve(battery("agm-test", Chemistry.AGM), Mode.AUTO)
        for telemetry in (
            TelemetrySnapshot(3.0, 14.0, 4.0, 25.0, fresh=False),
            TelemetrySnapshot(4.0, None, None, None, fresh=True),
        ):
            decision, domain_safety, request = self.evaluate_and_request(
                program, BatteryState(phase=Phase.MAIN), telemetry
            )
            self.assertEqual(domain_safety.state, SafetyState.DENY)
            self.assertIsNone(request)
            self.assertEqual(decision.confidence, "UNKNOWN")

    def test_safety_deny_and_execution_reject_have_no_physical_effect(self):
        program = self.resolver.resolve(battery("calcium-test", Chemistry.CALCIUM), Mode.AUTO)
        unsafe = TelemetrySnapshot(5.0, 17.0, 20.0, 60.0)
        _, deny, request = self.evaluate_and_request(
            program, BatteryState(phase=Phase.MAIN), unsafe
        )
        self.assertEqual(deny.state, SafetyState.DENY)
        self.assertIsNone(request)
        self.assertEqual(self.mock_boundary.requests, [])

        denied_intent = ExecutionIntent(
            14.4, 5.0, "SETPOINT", "rejected-decision", IntentSafetyContext(
                telemetry_state="FRESH", containment_state="CONTAINMENT"
            )
        )
        result = ExecutionSafetyPolicy(max_voltage_v=16.5, max_current_a=12.0).validate(denied_intent)
        self.assertEqual(result.outcome, SafetyOutcome.DENIED)
        self.assertEqual(self.mock_boundary.requests, [])

    def test_ambiguous_restore_is_observation_only(self):
        result = LifecycleRestoreClassifier().classify(
            None, legacy_state={"phase": "MIX", "profile": "CALCIUM"}
        )
        self.assertEqual(result.kind, RestoreKind.AMBIGUOUS)
        self.assertIsNone(result.snapshot)
        self.assertEqual(self.mock_boundary.requests, [])

    def test_v3_dry_run_modules_have_no_forbidden_runtime_dependencies(self):
        import application.charge_engine.generic as generic
        import application.charge_program.resolver as resolver
        import application.physical_boundary.mapper as boundary

        for module in (generic, resolver, boundary):
            with open(module.__file__, encoding="utf-8") as handle:
                source = handle.read()
            for forbidden in ("ChargeControllerV2", "HA", "ESPHome", "Modbus", "turn_on", "turn_off"):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
