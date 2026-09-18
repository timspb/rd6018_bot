import unittest
from pathlib import Path


class VerifiedOffExecutionTests(unittest.TestCase):
    def test_verified_off_surface_has_no_independent_executor(self):
        import runtime.output.bridge as bridge

        self.assertFalse(hasattr(bridge, "PhysicalBridgeExecutor"))

    def test_verified_off_remains_a_v2_owner_responsibility(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "execution_port.py").read_text(encoding="utf-8")
        self.assertIn("v2_owner.turn_off", source)
        self.assertIn("output_off", source)


if __name__ == "__main__":
    unittest.main()
