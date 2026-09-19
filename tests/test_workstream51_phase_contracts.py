import unittest

from application.charge_engine.phases import (
    CanonicalPhase, DeltaPolicy, HoldPolicy, InterruptionPolicy,
    PhaseContract, PhaseLifecycleRegistry, PhaseStatus, RecoveryPolicy,
    TimeoutPolicy, canonical_phase_contracts,
)


class PhaseLifecycleContractTests(unittest.TestCase):
    def test_all_canonical_phases_have_contracts(self):
        registry = PhaseLifecycleRegistry(canonical_phase_contracts())
        self.assertEqual(set(registry.ids()), {phase.value for phase in CanonicalPhase})

    def test_delta_contract_is_data_only(self):
        contract = PhaseLifecycleRegistry(canonical_phase_contracts()).get("MIX")
        self.assertEqual(contract.delta_policy.measurements, ("voltage", "current", "temperature"))
        self.assertEqual(contract.delta_policy.completion_condition, "confirmed_delta")

    def test_hold_contract_is_data_only(self):
        contract = PhaseLifecycleRegistry(canonical_phase_contracts()).get("HOLD")
        self.assertEqual(contract.hold_policy.start_condition, "delta_complete")
        self.assertEqual(contract.hold_policy.interruption, InterruptionPolicy.PAUSE)

    def test_invalid_timeout_contract_rejected(self):
        with self.assertRaises(ValueError):
            PhaseContract("X", ("entry",), ("exit",), (), TimeoutPolicy.NONE, 10.0, InterruptionPolicy.NONE, RecoveryPolicy.NONE)

    def test_contracts_are_immutable_and_have_no_safety_action(self):
        contract = PhaseLifecycleRegistry(canonical_phase_contracts()).get("MAIN")
        with self.assertRaises(AttributeError):
            contract.phase_id = "OTHER"
        module = __import__("application.charge_engine.phases.contracts", fromlist=["x"])
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("turn_on", source)
        self.assertNotIn("turn_off", source)
        self.assertNotIn("send(", source)


if __name__ == "__main__":
    unittest.main()
