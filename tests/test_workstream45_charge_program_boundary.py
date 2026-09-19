import unittest

from application.charge_program import (
    BatteryProfile,
    Chemistry,
    ManualProgramInput,
    Mode,
    ParameterOwner,
    resolve_charge_program,
)


class ChargeProgramBoundaryTests(unittest.TestCase):
    def test_auto_calcium_aliases_are_canonical_and_deterministic(self):
        first = resolve_charge_program(BatteryProfile("kak-72", "CA_CA", 72), "AUTO")
        second = resolve_charge_program(BatteryProfile("kak-72", "KAK", 72), Mode.AUTO)
        self.assertEqual(first, second)
        self.assertIs(first.chemistry, Chemistry.CALCIUM)
        self.assertEqual(first.mode, Mode.AUTO)
        self.assertEqual(first.program_id, "auto:calcium:kak-72")

    def test_auto_chemistries_have_complete_programs(self):
        for chemistry in ("CALCIUM", "EFB", "AGM"):
            with self.subTest(chemistry=chemistry):
                program = resolve_charge_program(BatteryProfile("battery", chemistry, 72), "AUTO")
                self.assertEqual([phase.phase_id for phase in program.phases], ["main", "mix"])
                self.assertTrue(program.timers)
                self.assertTrue(program.conditions)
                self.assertTrue(program.safety_references)
                for phase in program.phases:
                    self.assertEqual(phase.voltage.ceiling.owner, ParameterOwner.SAFETY_POLICY)
                    self.assertEqual(phase.current.ceiling.owner, ParameterOwner.SAFETY_POLICY)

    def test_manual_baic72_uses_explicit_operator_values(self):
        manual = ManualProgramInput(14.1, 5.0, 17.5, 3.5, 0.6, 0.6, 4.0)
        program = resolve_charge_program(BatteryProfile("Baic72", "CA_CA", 72), "MANUAL", manual)
        self.assertEqual(program.program_id, "manual:Baic72")
        self.assertEqual(program.mode, Mode.MANUAL)
        self.assertEqual(program.phases[1].voltage.target.value, 17.5)
        self.assertEqual(program.phases[1].conditions[0].owner, ParameterOwner.MANUAL_PROGRAM)
        self.assertEqual(program.phases[1].voltage.ceiling.owner, ParameterOwner.SAFETY_POLICY)

    def test_manual_requires_explicit_parameters(self):
        with self.assertRaises(ValueError):
            resolve_charge_program(BatteryProfile("Baic72", "CA_CA", 72), "MANUAL")

    def test_auto_rejects_manual_override(self):
        manual = ManualProgramInput(14.1, 5.0, 17.5, 3.5, 0.6, 0.6, 4.0)
        with self.assertRaises(ValueError):
            resolve_charge_program(BatteryProfile("Baic72", "CA_CA", 72), "AUTO", manual)

    def test_domain_package_has_no_production_wiring(self):
        import application.charge_program.resolver as resolver

        self.assertNotIn("charge_controller_v2", resolver.__file__)
        self.assertNotIn("hass_api", resolver.__file__)


if __name__ == "__main__":
    unittest.main()
