import unittest
from types import SimpleNamespace
from application.recipe_restart_limits import existing_start_limits


class ExistingLimitsTests(unittest.TestCase):
    def setUp(self):
        self.host = SimpleNamespace(OVP_OFFSET=0.1, OCP_OFFSET=0.1,
                                    _cap_current=lambda value: min(value, 7.2))

    def test_reuses_start_offsets(self):
        result = existing_start_limits(self.host, voltage_v=14.7, current_a=1.0,
                                       voltage_ceiling_v=15.5)
        self.assertAlmostEqual(result[0], 14.8)
        self.assertAlmostEqual(result[1], 1.1)
        self.assertEqual(result[2], 15.5)

    def test_existing_envelope_and_current_cap_are_enforced(self):
        for v, i in ((16.0, 1.0), (14.7, 10.0)):
            with self.assertRaises(ValueError):
                existing_start_limits(self.host, voltage_v=v, current_a=i,
                                      voltage_ceiling_v=15.5)
