"""RS-1C: native recipe UI metadata derived from canonical specs and browser behavior."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from runtime.charge.programs.recipe_studio_native_catalog import native_studio_catalog
from runtime.charge.programs.recipe_studio_import import inspect_native_document
from runtime.charge.programs.native_recipe_catalog import native_recipes

ROOT = Path(__file__).resolve().parents[1]
CATALOG_JS = ROOT / "tools" / "recipe_studio_native_catalog.js"
EDITOR_JS = ROOT / "tools" / "recipe_studio_native_editor.js"
CLI = ROOT / "tools" / "recipe_studio_offline.py"


def node_native(payload: dict) -> dict:
    script = r'''
const fs = require("fs"), vm = require("vm");
const ids = ["nativeStudio","nativePreset","nativeName","nativeVersion",
"nativeReset","nativeExport","nativeCheck","nativeSave","nativeImportBtn","nativeFile","nativeStatus",
"nativeFields","nativeJSON","nativeError"];
const objects = Object.fromEntries(ids.map(id => [id,{
 value: id === "nativeName" ? "my_efb" : id === "nativeVersion" ? "1" : "",
 innerHTML: "", textContent:"", dataset:{},
 addEventListener(name,cb){this["on_"+name]=cb;},
 click(){}, files:[],
}]));
const window = {};
const document = {getElementById(id){return objects[id];}};
const ctx = {window,document,console,URL,Blob,setTimeout};
vm.runInNewContext(fs.readFileSync(process.argv[1],"utf8"),ctx);
vm.runInNewContext(fs.readFileSync(process.argv[2],"utf8"),ctx);
const data = JSON.parse(process.argv[3]);
let result;
try {result={ok:true,value:window.RD6018NativeStudio.inspectDraft(
 data.name,data.version,data.base,data.overrides)}}
catch(err){result={ok:false,error:String(err.message)}}
result.rows=objects.nativeFields.innerHTML.includes("charge.main");
result.status=objects.nativeStatus.textContent;
process.stdout.write(JSON.stringify(result));
'''
    p = subprocess.run(["node", "-e", script, str(CATALOG_JS), str(EDITOR_JS),
                        json.dumps(payload)], capture_output=True, text=True, check=True, timeout=12)
    return json.loads(p.stdout)


class NativeStudioUITests(unittest.TestCase):
    def test_checked_in_ui_catalog_is_exact_derived_snapshot(self):
        original = CATALOG_JS.read_text(encoding="utf-8").strip()
        prefix = "window.RD6018_NATIVE_CATALOG = "
        self.assertTrue(original.startswith(prefix))
        self.assertTrue(original.endswith(";"))
        static = json.loads(original[len(prefix):-1])
        self.assertEqual(static, native_studio_catalog())
        self.assertEqual(len(static["recipes"]), 12)
        self.assertEqual({r["recipe_id"] for r in static["recipes"]},
                         {r.recipe_id for r in native_recipes()})

    def test_parameter_metadata_available_for_all_twelve_recipes(self):
        for r in native_studio_catalog()["recipes"]:
            self.assertTrue(r["parameters"])
            for param in r["parameters"]:
                for name in ("key","description","unit","owner","default","type",
                             "minimum","maximum","editable","change_effect"):
                    self.assertIn(name, param)
                if param["editable"]:
                    self.assertIn(param["type"], ("int","float"))
                self.assertNotEqual(param["unit"], "")

    def test_ui_valid_default_draft_matches_existing_backend(self):
        payload = {"name":"my_efb","version":1,"base":"native_efb_normal",
                   "overrides":{"charge.main.efb_voltage_v":14.6}}
        r = node_native(payload)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["rows"])
        self.assertEqual(r["value"]["draft"]["overrides"], payload["overrides"])
        checked = inspect_native_document(r["value"])
        self.assertEqual(checked.draft.base_recipe_id, payload["base"])

    def test_ui_refuses_bad_types_ranges_unknown_and_wrong_revision(self):
        for item in (
            {"name":"native_existing","version":1,"base":"native_efb_normal","overrides":{}},
            {"name":"mine","version":0,"base":"native_efb_normal","overrides":{}},
            {"name":"mine","version":1,"base":"native_efb_normal","overrides":{"unknown":1}},
            {"name":"mine","version":1,"base":"native_efb_normal","overrides":{"charge.main.efb_voltage_v":99}},
            {"name":"mine","version":1,"base":"native_efb_normal","overrides":{"charge.main.efb_voltage_v":"14.7"}},
            {"name":"mine","version":1,"base":"native_efb_normal","overrides":{"charge.main.current_c_rate":0.11}},
        ):
            with self.subTest(item=item):
                self.assertFalse(node_native(item)["ok"])

    def test_cli_snapshot_command_and_draft_check(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"studio.js"
            p = subprocess.run([sys.executable,str(CLI),"catalog-native","--output",str(path)],
                               cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(path.read_bytes(),CATALOG_JS.read_bytes())
            self.assertFalse(json.loads(p.stdout)["physical_start_authorized"])
            draft=Path(temp)/"draft.json"
            draft.write_text(json.dumps({"name":"my_efb","version":1,"draft":{
                "schema":1,"base_recipe_id":"native_efb_normal",
                "execution_kind":"native_authority","overrides":{}}}),encoding="utf-8")
            check=subprocess.run([sys.executable,str(CLI),"check-native","--file",str(draft)],
                                 cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(check.returncode,0,check.stderr)


if __name__ == "__main__":
    unittest.main()
