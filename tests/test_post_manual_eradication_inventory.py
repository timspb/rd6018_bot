import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostManualEradicationInventoryTests(unittest.TestCase):
    def test_inventory_is_exact_head_machine_readable_and_counts_match(self):
        path = ROOT / "docs" / "POST_MANUAL_ERADICATION_INVENTORY.json"
        inventory = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(inventory["baseline_sha"], "1f8d9c45c9b543dde7a57f78b6385d01012e7b4f")
        production = inventory["production_reachable"] + inventory["schema_or_protocol_boundaries"]
        docs_tests = inventory["non_production_tests_or_docs_only"]
        counts = inventory["counts"]
        self.assertEqual(sum(1 for item in production if item["category"] == "A"), counts["A_obsolete_behavioral_fallback_or_duplicate_owner"])
        self.assertEqual(sum(1 for item in production if item["category"] == "B"), counts["B_historical_name_in_active_canonical_functionality"])
        self.assertEqual(sum(1 for item in production if item["category"] == "C"), counts["C_persisted_or_protocol_schema_boundary"])
        self.assertEqual(sum(1 for item in production if item["category"] == "D"), counts["D_dead_or_unreachable_code_remaining"])
        self.assertEqual(sum(1 for item in docs_tests if item["category"] == "E"), counts["E_tests_or_docs_only"])
        self.assertEqual(1, counts["A_obsolete_behavioral_fallback_or_duplicate_owner"])
        self.assertEqual(0, counts["D_dead_or_unreachable_code_remaining"])

    def test_confirmed_dead_shadow_cluster_is_absent_and_not_reexported(self):
        for rel in (
            "runtime/output/bridge/shadow.py",
            "runtime/output/bridge/mapping.py",
            "runtime/output/bridge/contract.py",
        ):
            self.assertFalse((ROOT / rel).exists(), rel)
        bridge_init = (ROOT / "runtime/output/bridge/__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("ShadowOutputBridge", bridge_init)
        self.assertNotIn("LegacyActuatorCommand", bridge_init)
        production_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in ROOT.rglob("*.py")
            if "tests" not in path.parts and "__pycache__" not in path.parts
        )
        for removed_name in ("ShadowOutputBridge", "map_safe_output_intent", "LegacyActuatorCommand"):
            self.assertNotIn(removed_name, production_sources)


if __name__ == "__main__":
    unittest.main()
