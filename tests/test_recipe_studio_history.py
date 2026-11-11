"""RS-2 library history, comparison, immutable revision and archive API."""
from __future__ import annotations

from pathlib import Path

from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from test_recipe_studio_local_bridge import TestStudioBridge, STEP, NATIVE


class TestStudioHistory(TestStudioBridge):
    # Inherit the real HTTP lifecycle; tests are run against a loopback server.
    def test_history_load_compare_and_archive_for_both_kinds(self):
        for kind, source in (("step", STEP), ("native", NATIVE)):
            with self.subTest(kind=kind):
                base = {"kind": kind, "recipe": source}
                self.assertEqual(self.request("POST", "/api/save", base)[0], 200)
                revised = dict(source, version=2)
                if kind == "step":
                    revised["steps"] = [
                        {**STEP["steps"][0], "params": {"voltage_v": 14.8, "current_a": 2.0}},
                        *STEP["steps"][1:],
                    ]
                else:
                    revised["draft"] = {
                        **NATIVE["draft"],
                        "overrides": {"charge.main.efb_voltage_v": 14.6},
                    }
                self.assertEqual(self.request("POST", "/api/save",
                                              {"kind": kind, "recipe": revised})[0], 200)
                status, list_response = self.request("POST", "/api/list", {"kind": kind})
                self.assertEqual(status, 200, list_response)
                items = list_response["items"]
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["versions"], [1, 2])
                self.assertFalse(items[0]["archived"])
                name = items[0]["id"]
                status, loaded = self.request("POST", "/api/load",
                                              {"kind": kind, "id": name, "version": 1})
                self.assertEqual(status, 200, loaded)
                self.assertEqual(loaded["recipe"], source)
                status, diff = self.request("POST", "/api/compare",
                                            {"kind": kind, "id": name, "left": 1, "right": 2})
                self.assertEqual(status, 200, diff)
                self.assertTrue(diff["changed"])
                self.assertIn("--- v1", diff["diff"])
                self.assertIn("+++ v2", diff["diff"])
                self.assertFalse(diff["physical_start_authorized"])
                folder = Path(self.temp.name) / ("steps" if kind == "step" else "native") / name
                first = (folder / "v1.json").read_bytes()
                second = (folder / "v2.json").read_bytes()
                status, archive = self.request("POST", "/api/archive",
                                               {"kind": kind, "id": name})
                self.assertEqual(status, 200, archive)
                self.assertTrue(archive["archived"])
                self.assertEqual((folder / "v1.json").read_bytes(), first)
                self.assertEqual((folder / "v2.json").read_bytes(), second)
                self.assertEqual(self.request("POST", "/api/list", {"kind": kind})[1]
                                 ["items"][0]["archived"], True)
                self.assertEqual(self.request("POST", "/api/load", {
                    "kind": kind, "id": name, "version": 2})[0], 200)
                self.assertEqual(self.request("POST", "/api/save", {
                    "kind": kind, "recipe": dict(source, version=3)})[0], 422)
                self.assertEqual(self.request("POST", "/api/archive", {
                    "kind": kind, "id": name})[0], 422)

    def test_no_paths_or_production_apis_in_library_operations(self):
        self.assertEqual(self.request("POST", "/api/list", {"kind": "native"})[1]["items"], [])
        for route, payload in (
            ("/api/load", {"kind": "step", "id": "../bad", "version": 1}),
            ("/api/compare", {"kind": "native", "id": "..", "left": 1, "right": 2}),
            ("/api/archive", {"kind": "step", "id": "../escape"}),
            ("/api/list", {"kind": "step", "root": "/opt/services"}),
            ("/api/load", {"kind": "native", "id": "test_native", "version": True}),
        ):
            with self.subTest(route=route, payload=payload):
                self.assertEqual(self.request("POST", route, payload)[0], 422)

    def test_history_endpoints_require_the_same_operator_capability(self):
        for route in ("/api/list", "/api/load", "/api/archive", "/api/compare"):
            with self.subTest(route=route):
                for bad in ({"token": False}, {"origin": False}, {"host": False}):
                    status, _ = self.request("POST", route, {"kind": "step"}, **bad)
                    self.assertEqual(status, 403)

    def test_archived_libraries_block_direct_new_revisions(self):
        for kind, source in (("step", STEP), ("native", NATIVE)):
            with self.subTest(kind=kind):
                self.assertEqual(self.request("POST", "/api/save", {
                    "kind": kind, "recipe": source})[0], 200)
                identity = source["id"] if kind == "step" else source["name"]
                self.assertEqual(self.request("POST", "/api/archive", {
                    "kind": kind, "id": identity})[0], 200)
                folder = Path(self.temp.name) / kind.replace("step", "steps")
                if kind == "step":
                    library = RecipeLibrary(folder, max_voltage_v=15.5, max_current_a=7.2)
                    with self.assertRaisesRegex(ValueError, "archived"):
                        library.save(dict(source, version=2))
                else:
                    library = NativeRecipeDraftLibrary(folder)
                    with self.assertRaisesRegex(ValueError, "archived"):
                        library.save(identity, 2, source["draft"])

    def test_identical_revisions_have_no_diff(self):
        self.assertEqual(self.request("POST", "/api/save",
                                     {"kind": "step", "recipe": STEP})[0], 200)
        status, result = self.request("POST", "/api/compare", {
            "kind": "step", "id": "test_step", "left": 1, "right": 1,
        })
        self.assertEqual(status, 200, result)
        self.assertFalse(result["changed"])
        self.assertEqual(result["diff"], "")
