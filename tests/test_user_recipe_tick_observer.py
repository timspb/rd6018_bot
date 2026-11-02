import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from application.charge_session_tick import run_charge_session_tick
from runtime.charge.programs.recipe_schema import parse_recipe


class TickObserverTests(unittest.IsolatedAsyncioTestCase):
    async def test_observation_binding_records_without_lifecycle_action(self):
        recipe = parse_recipe({"id":"probe","version":1,"steps":[
            {"action":"off","params":{},"until":{"after_seconds":2}}
        ]}, max_voltage_v=15.5, max_current_a=7.2)
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "series.jsonl"
            host = SimpleNamespace(_recipe_observation_binding=(recipe,"run1",output),
                                   _guarded_restore_activated_off=True,last_update_time=None)
            result = await run_charge_session_tick(host, voltage=12.4,current=0.2,
                temp_ext=26.0,is_cv=False,ah=1.0)
            self.assertEqual(result,{})
            row = json.loads(output.read_text(encoding="utf-8").strip())
            self.assertEqual(row["measurements"]["voltage"],12.4)
            self.assertEqual(row["session"],"run1")
