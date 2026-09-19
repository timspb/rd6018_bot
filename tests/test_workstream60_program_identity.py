import pathlib
import unittest

from application.charge_program import BatteryProfile, Chemistry, ProgramIdentity, ProgramIdentityRegistry


ROOT = pathlib.Path(__file__).parents[1]


class ProgramIdentityAuthorityTests(unittest.TestCase):
    def test_alias_resolves_to_stable_canonical_id(self):
        registry = ProgramIdentityRegistry()
        self.assertEqual(registry.canonical_id("CA_CA"), "CALCIUM")
        self.assertEqual(registry.canonical_id("KAK"), "CALCIUM")
        self.assertEqual(registry.canonical_id("Ca/Ca"), "CALCIUM")

    def test_canonical_id_is_stable(self):
        registry = ProgramIdentityRegistry()
        self.assertEqual(registry.canonical_ids(), ("AGM", "CALCIUM", "EFB"))
        self.assertEqual(registry.chemistry("CALCIUM"), Chemistry.CALCIUM)

    def test_duplicate_alias_is_rejected(self):
        with self.assertRaises(ValueError):
            ProgramIdentityRegistry((
                ProgramIdentity("A", Chemistry.AGM, ("DUP",)),
                ProgramIdentity("B", Chemistry.EFB, ("DUP",)),
            ))

    def test_charge_program_model_stores_canonical_identity(self):
        profile = BatteryProfile("battery", "CA_CA", 72)
        self.assertEqual(profile.chemistry, Chemistry.CALCIUM)

    def test_no_secondary_alias_authority(self):
        self.assertFalse((ROOT / "application" / "charge_program" / "aliases.py").exists())
        source = (ROOT / "application" / "charge_program" / "program_ids.py").read_text(encoding="utf-8")
        self.assertNotIn("CA_CA", source)
        self.assertNotIn("KAK", source)


if __name__ == "__main__":
    unittest.main()
