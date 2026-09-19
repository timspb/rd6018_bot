import unittest

from application.charge_program import requested_manual_program_input


class RequestedManualProgramTests(unittest.TestCase):
    def test_requested_main_and_mix_values(self):
        program = requested_manual_program_input()
        self.assertEqual((program.main_voltage_v, program.main_current_a), (14.1, 5.0))
        self.assertEqual((program.main_imin_a, program.main_hold_hours), (2.30, 0.001))
        self.assertEqual((program.mix_voltage_v, program.mix_current_a), (15.5, 3.5))
        self.assertEqual((program.delta_voltage_v, program.delta_current_a), (0.001, 0.001))
        self.assertEqual(program.hold_hours, 0.04)


if __name__ == "__main__":
    unittest.main()
