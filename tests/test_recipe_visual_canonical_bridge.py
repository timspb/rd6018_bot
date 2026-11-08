"""Offline RS-1A bridge parity with the canonical Python recipe owner; no device IO."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

from runtime.charge.programs.recipe_preflight import inspect_recipe
from runtime.charge.programs.recipe_schema import parse_recipe

ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "tools" / "recipe_visual_editor_prototype.html"
START = "// RS-1A: pure offline adapter."
END = "function render()"


def javascript_bridge(operation: str, data: dict, *, max_v=15.5, max_i=7.2):
    html = PROTOTYPE.read_text(encoding="utf-8")
    code = html.split(START, 1)[1].split(END, 1)[0]
    source = (
        START + code
        + "\nconst input=JSON.parse(process.argv[1]);\n"
        + "try { const result=input.operation==='export' "
        + "?canonicalFromVisual(input.data,input.data.name,input.data.version,input.maxV,input.maxI)"
        + ":visualFromCanonical(input.data,input.maxV,input.maxI);"
        + "process.stdout.write(JSON.stringify({ok:true,value:result}));"
        + "} catch(error) {process.stdout.write(JSON.stringify({ok:false,error:error.message}));}\n"
    )
    value = json.dumps({"operation": operation, "data": data, "maxV": max_v, "maxI": max_i})
    p = subprocess.run(["node", "-e", source, value], capture_output=True, text=True, timeout=10, check=True)
    return json.loads(p.stdout)


def visual(steps, *, repeats=0, name="recipe_A", version=1):
    return {"schema": "rd6018.recipe_visual_draft.v1", "name": name, "version": version,
            "chemistry": "EFB", "capacity_ah": 72, "repeat_count": repeats, "stages": steps}


def step(kind, *, v=0, i=0, threshold=30, cond="after_seconds", mode="CUSTOM", minutes=0):
    return {"on": kind == "set", "kind": kind, "mode": mode, "v": v, "i": i,
            "min": minutes, "cond": cond, "threshold": threshold}


class RecipeVisualCanonicalBridgeTests(unittest.TestCase):
    def test_canonical_roundtrip_and_python_parser(self):
        stages = [step("set", v=14.7, i=3, cond="current_lte", threshold=1),
                  step("off"), step("wait", threshold=15)]
        data = visual(stages)
        exported = javascript_bridge("export", data)
        self.assertTrue(exported["ok"], exported)
        recipe = parse_recipe(exported["value"], max_voltage_v=15.5, max_current_a=7.2)
        self.assertTrue(inspect_recipe(recipe).admissible_structure)
        imported = javascript_bridge("import", exported["value"])
        self.assertTrue(imported["ok"], imported)
        self.assertEqual(imported["value"]["stages"], stages)
        self.assertEqual(imported["value"]["name"], data["name"])

    def test_native_stage_is_not_converted(self):
        result = javascript_bridge("export", visual([step("native", mode="MAIN")]))
        self.assertFalse(result["ok"])
        self.assertIn("native", result["error"])

    def test_named_native_mode_is_not_downgraded_to_custom(self):
        result = javascript_bridge("export", visual([step("set", mode="MAIN", v=14, i=1)]))
        self.assertFalse(result["ok"])
        self.assertIn("CUSTOM", result["error"])

    def test_repeats_cannot_be_silently_discarded(self):
        result = javascript_bridge("export", visual([step("off")], repeats=2))
        self.assertFalse(result["ok"])
        self.assertIn("Повторения", result["error"])

    def test_hidden_time_budget_cannot_be_discarded(self):
        result = javascript_bridge("export", visual([step("set", v=14, i=1, minutes=30)]))
        self.assertFalse(result["ok"])
        self.assertIn("времени", result["error"])

    def test_wait_requires_off(self):
        result = javascript_bridge("export", visual([step("set", v=14, i=2), step("wait")]))
        self.assertFalse(result["ok"])
        self.assertIn("WAIT", result["error"])

    def test_limits_enforced_for_export_and_import(self):
        result = javascript_bridge("export", visual([step("set", v=16, i=1)]))
        self.assertFalse(result["ok"])
        candidate = {"id": "safe", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.0, "current_a": 8.0}, "until": {"after_seconds": 30}}]}
        self.assertFalse(javascript_bridge("import", candidate)["ok"])

    def test_off_wait_do_not_hold_setpoints(self):
        bad = visual([step("off", v=14, i=0)])
        self.assertFalse(javascript_bridge("export", bad)["ok"])
        candidate = {"id": "bad", "version": 1, "steps": [
            {"action": "wait", "params": {}, "until": {"after_seconds": 30}}]}
        self.assertFalse(javascript_bridge("import", candidate)["ok"])

    def test_invalid_conditions_are_rejected(self):
        data = visual([step("set", v=14, i=1, cond="after_seconds", threshold=0)])
        self.assertFalse(javascript_bridge("export", data)["ok"])
        data = visual([step("set", v=14, i=1, cond="unexpected", threshold=1)])
        self.assertFalse(javascript_bridge("export", data)["ok"])

    def test_import_rejects_extra_fields_or_unknown_steps(self):
        data = {"id": "r", "version": 1, "steps": [
            {"action": "native", "params": {}, "until": {"after_seconds": 4}}]}
        self.assertFalse(javascript_bridge("import", data)["ok"])
        data["steps"][0]["action"] = "off"
        data["steps"][0]["hidden"] = "unused"
        self.assertFalse(javascript_bridge("import", data)["ok"])


if __name__ == "__main__":
    unittest.main()
