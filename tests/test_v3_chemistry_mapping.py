import ast
import pathlib
import unittest

from runtime.charge import ChemistryProfile, ProductionChemistry, map_production_chemistry


class V3ChemistryMappingTests(unittest.TestCase):
    def test_explicit_production_mapping(self):
        self.assertEqual(ChemistryProfile.CALCIUM, map_production_chemistry(ProductionChemistry.CA_CA))
        self.assertEqual(ChemistryProfile.CALCIUM, map_production_chemistry("Ca/Ca"))
        self.assertEqual(ChemistryProfile.CALCIUM, map_production_chemistry("FLOODED"))
        self.assertEqual(ChemistryProfile.CALCIUM, map_production_chemistry("CUSTOM"))
        self.assertEqual(ChemistryProfile.AGM, map_production_chemistry("AGM"))
        self.assertEqual(ChemistryProfile.EFB, map_production_chemistry("EFB"))

    def test_unknown_chemistry_fails_at_boundary(self):
        with self.assertRaises(ValueError):
            map_production_chemistry("unknown")

    def test_domain_has_no_infrastructure_imports(self):
        root = pathlib.Path(__file__).parents[1] / "runtime" / "charge"
        forbidden = {"pb_domain", "hass_api", "aiogram", "rd_control_mode", "safe_output", "bot_legacy"}
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden, str(path))


if __name__ == "__main__":
    unittest.main()
