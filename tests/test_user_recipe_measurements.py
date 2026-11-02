import json
import tempfile
import unittest
from pathlib import Path
from runtime.charge.programs.recipe_schema import parse_recipe
from runtime.charge.programs.recipe_measurements import record_measurement

class MeasurementTests(unittest.TestCase):
    def test_measurement_is_pinned_and_bad_values_rejected(self):
        recipe = parse_recipe({"id":"lab","version":1,"steps":[
            {"action":"off","params":{},"until":{"after_seconds":1}}
        ]}, max_voltage_v=15.5,max_current_a=7.2)
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "measurements.jsonl"
            record_measurement(target,recipe=recipe,session_id="s",timestamp_s=1,
                               values={"voltage":12.3,"current":0.1,"temperature":27})
            row = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["digest"], recipe.digest)
            self.assertEqual(row["measurements"]["voltage"],12.3)
            with self.assertRaises(ValueError):
                record_measurement(target,recipe=recipe,session_id="s",timestamp_s=2,
                                   values={"voltage":float("nan")})
