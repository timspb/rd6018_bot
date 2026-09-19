import unittest

from application.charge_engine import (
    BatteryState,
    ChargeProgramRegistry,
    GenericChargeEngine,
    StaticChargeProgramProvider,
    TelemetrySnapshot,
)
from application.charge_program import (
    BatteryProfile,
    ChargeProgram,
    Chemistry,
    Condition,
    CurrentPolicy,
    Mode,
    OwnedValue,
    ParameterOwner,
    Phase,
    SafetyReference,
    TransitionRule,
    VoltagePolicy,
)


def make_program(program_id="lab-program"):
    owner = ParameterOwner.BATTERY_PROFILE
    safety = ParameterOwner.SAFETY_POLICY
    first = Phase(
        "alpha",
        VoltagePolicy(OwnedValue("alpha_v", 13.2, owner), OwnedValue("v_ceiling", 16.5, safety)),
        CurrentPolicy(OwnedValue("alpha_i", 1.0, owner), OwnedValue("i_ceiling", 12.0, safety)),
        conditions=(Condition("ready", "plugin condition", owner),),
    )
    second = Phase(
        "omega",
        VoltagePolicy(OwnedValue("omega_v", 14.2, owner), OwnedValue("v_ceiling", 16.5, safety)),
        CurrentPolicy(OwnedValue("omega_i", 0.5, owner), OwnedValue("i_ceiling", 12.0, safety)),
    )
    return ChargeProgram(
        program_id=program_id,
        mode=Mode.AUTO,
        battery_profile=BatteryProfile("arbitrary-battery", Chemistry.CALCIUM, 40),
        chemistry=Chemistry.CALCIUM,
        phases=(first, second),
        voltage_policy=first.voltage,
        current_policy=first.current,
        timers=(),
        conditions=first.conditions,
        safety_references=(SafetyReference("telemetry", 300.0),),
        transitions=(TransitionRule("alpha", "omega", "ready"),),
    )


class GenericChargeEngineTests(unittest.TestCase):
    def test_new_program_works_without_engine_changes(self):
        program = make_program("new-plugin-program")
        decision = GenericChargeEngine().evaluate(
            program,
            BatteryState(phase="alpha", condition_values=(("ready", True),)),
            TelemetrySnapshot(1.0, 13.0, 1.0, 20.0),
        )
        self.assertEqual(decision.next_phase, "omega")
        self.assertEqual(decision.desired_voltage_v, 13.2)

    def test_registry_register_lookup_unregister(self):
        registry = ChargeProgramRegistry()
        provider = StaticChargeProgramProvider(make_program("temporary"))
        registry.register(provider)
        self.assertEqual(registry.lookup("temporary").program.program_id, "temporary")
        registry.unregister("temporary")
        self.assertEqual(registry.available(), ())
        with self.assertRaises(KeyError):
            registry.lookup("temporary")

    def test_unknown_program_and_duplicate_are_rejected(self):
        registry = ChargeProgramRegistry()
        registry.register(StaticChargeProgramProvider(make_program("known")))
        with self.assertRaises(ValueError):
            registry.register(StaticChargeProgramProvider(make_program("known")))
        with self.assertRaises(KeyError):
            registry.lookup("unknown")

    def test_deterministic_generic_decision(self):
        program = make_program()
        state = BatteryState(phase="alpha")
        telemetry = TelemetrySnapshot(1.0, 13.0, 1.0, 20.0)
        first = GenericChargeEngine().evaluate(program, state, telemetry)
        second = GenericChargeEngine().evaluate(program, state, telemetry)
        self.assertEqual(first, second)

    def test_engine_has_no_chemistry_or_battery_name_branching(self):
        import application.charge_engine.generic as module

        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("AGM", "EFB", "CALCIUM", "Baic72", "ChargeControllerV2", "turn_on", "turn_off"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
