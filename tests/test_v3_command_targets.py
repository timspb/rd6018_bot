import unittest

from runtime.output.bridge import HardwareSnapshot
from runtime.physical.commands import PhysicalCommand, PhysicalCommandTarget, validate_target, verify_target
from runtime.physical.commands.verification import compare_dual


class CommandTargetTests(unittest.TestCase):
    def target(self, command=PhysicalCommand.SET_CURRENT, **expected):
        return PhysicalCommandTarget(command, {"value": .55}, expected or {"current_setpoint": .55},
                                     {field: .05 for field in (expected or {"current_setpoint": .55})}, 100)

    def snapshot(self, **changes):
        values = dict(timestamp=100, connection_state="connected", output_state=False,
                      measured_voltage=0, measured_current=0, configured_voltage=13.94,
                      configured_current=.55, ovp=16.7, ocp=12, temperature=31)
        values.update(changes)
        return HardwareSnapshot(**values)

    def test_target_validation_and_expected_readback(self):
        target = self.target()
        self.assertTrue(validate_target(target).valid)
        result = verify_target(target, self.snapshot(), connector="ha_esp", now=100)
        self.assertEqual(result.result, "MATCH")

    def test_mismatch_and_stale_readback(self):
        target = self.target()
        mismatch = verify_target(target, self.snapshot(configured_current=.8), connector="ha_esp", now=100)
        stale = verify_target(target, self.snapshot(timestamp=80), connector="ha_esp", now=100)
        self.assertEqual(mismatch.result, "MISMATCH")
        self.assertEqual(stale.result, "MISMATCH")

    def test_disable_and_dual_comparison(self):
        target = PhysicalCommandTarget(PhysicalCommand.DISABLE_OUTPUT, {}, {"output_state": False, "current": 0},
                                       {"output_state": 0, "current": .01}, 100)
        left = verify_target(target, self.snapshot(), connector="ha_esp", now=100)
        right = verify_target(target, self.snapshot(), connector="esp_direct", now=100)
        self.assertEqual(compare_dual(target, (left, right)).comparison, "MATCH")

    def test_enable_is_not_a_supported_target(self):
        self.assertNotIn("ENABLE", {command.value for command in PhysicalCommand})
