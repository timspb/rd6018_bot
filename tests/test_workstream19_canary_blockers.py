import ast
import unittest
from pathlib import Path

from application.canary_blockers import (
    BlockerCategory,
    BlockerStatus,
    CanaryBlocker,
    CanaryBlockerRegistry,
    CanaryBlockerSnapshot,
    live_evaluation_blockers,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream19CanaryBlockerTests(unittest.TestCase):
    def test_live_blockers_are_registered_and_classified(self):
        registry = live_evaluation_blockers()
        self.assertGreaterEqual(len(registry.active), 5)
        self.assertIn(BlockerCategory.SAFETY, {item.category for item in registry.active})
        self.assertIn(BlockerCategory.APPROVAL, {item.category for item in registry.active})
        self.assertTrue(all(item.required_evidence and item.resolution_criteria for item in registry.active))

    def test_duplicate_ids_and_incomplete_resolution_are_rejected(self):
        blocker = CanaryBlocker("x", BlockerCategory.OPERATIONAL, "d", "s", "i", "o", ("e",), ("r",))
        registry = CanaryBlockerRegistry().register(blocker)
        with self.assertRaises(ValueError):
            registry.register(blocker)
        with self.assertRaises(ValueError):
            CanaryBlockerRegistry().register(CanaryBlocker("y", BlockerCategory.OPERATIONAL, "d", "s", "i", "o", (), ("r",)))

    def test_snapshot_is_read_only_and_does_not_imply_approval(self):
        registry = live_evaluation_blockers()
        snapshot = CanaryBlockerSnapshot(tuple(item.id for item in registry.active), {item.id: item.status.value for item in registry.active}, {"complete": False})
        self.assertEqual(len(snapshot.active_blockers), 5)
        self.assertNotIn("approve", snapshot.progress)

    def test_no_execution_or_approval_side_effects(self):
        source = (ROOT / "application" / "canary_blockers.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "paramiko", "requests", "esphome", "serial"})
        for token in ("output_on", "output_off", "set_voltage", "set_current", "controller.start", "controller.stop", "create_approval"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
