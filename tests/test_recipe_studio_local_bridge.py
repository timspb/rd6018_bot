"""RS-1D: local-only Recipe Studio transport acceptance and immutability."""
from __future__ import annotations

import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from tools.recipe_studio_local import StudioHTTPServer

STEP = {"id": "test_step", "version": 1, "steps": [
    {"action": "set", "params": {"voltage_v": 14.7, "current_a": 2.0},
     "until": {"after_seconds": 20}},
    {"action": "off", "params": {}, "until": {"after_seconds": 5}},
    {"action": "wait", "params": {}, "until": {"after_seconds": 5}},
]}
NATIVE = {"name": "test_native", "version": 1, "draft": {
    "schema": 1, "base_recipe_id": "native_efb_normal",
    "execution_kind": "native_authority", "overrides": {},
}}


class TestStudioBridge(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.server = StudioHTTPServer(("127.0.0.1", 0), Path(self.temp.name))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method, path, document=None, token=True,
                origin=True, host=True, content_type="application/json", extra_headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Host": f"127.0.0.1:{self.server.server_port}" if host else "attacker.example",
                   "Content-Type": content_type}
        if token:
            headers["X-Recipe-Studio-Token"] = self.server.token
        if origin:
            headers["Origin"] = self.server.origin
        if extra_headers:
            headers.update(extra_headers)
        payload = json.dumps(document) if document is not None else None
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        body = response.read()
        status = response.status
        conn.close()
        try:
            return status, json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return status, body

    def test_same_origin_native_and_step_save_with_readback(self):
        for kind, recipe in (("step", STEP), ("native", NATIVE)):
            with self.subTest(kind=kind):
                for path in ("/api/check", "/api/save"):
                    status, response = self.request("POST", path, {"kind": kind, "recipe": recipe})
                    self.assertEqual(status, 200, response)
                    self.assertEqual(response["status"],
                                     "VALIDATED" if path == "/api/check" else "SAVED")
                    self.assertFalse(response["physical_start_authorized"])
                saved = Path(self.temp.name) / ("steps" if kind == "step" else "native")
                doc = saved / (recipe["id"] if kind == "step" else recipe["name"]) / "v1.json"
                self.assertTrue(doc.exists())
                self.assertEqual(json.loads(doc.read_text())["version"], 1)

    def test_second_version_immutable_and_stale_rejected(self):
        for kind, data in (("step", STEP), ("native", NATIVE)):
            with self.subTest(kind=kind):
                self.assertEqual(self.request("POST", "/api/save",
                                 {"kind": kind, "recipe": data})[0], 200)
                parent = Path(self.temp.name) / ("steps" if kind == "step" else "native")
                item = parent / (data["id"] if kind == "step" else data["name"])
                before = (item / "v1.json").read_bytes()
                self.assertEqual(self.request("POST", "/api/save",
                                 {"kind": kind, "recipe": data})[0], 422)
                edited = dict(data, version=2)
                self.assertEqual(self.request("POST", "/api/save",
                                 {"kind": kind, "recipe": edited})[0], 200)
                self.assertEqual((item / "v1.json").read_bytes(), before)
                self.assertTrue((item / "v2.json").exists())
                self.assertEqual(self.request("POST", "/api/save",
                                 {"kind": kind, "recipe": dict(data, version=4)})[0], 422)

    def test_request_rejects_csrf_host_and_wrong_content_type(self):
        payload = {"kind": "step", "recipe": STEP}
        for kwargs in ({"token": False}, {"origin": False},
                       {"host": False}, {"content_type": "text/plain"}):
            with self.subTest(kwargs=kwargs):
                self.assertNotEqual(self.request("POST", "/api/save", payload, **kwargs)[0], 200)
        self.assertFalse((Path(self.temp.name) / "steps").exists())

    def test_no_arbitrary_file_paths_and_native_draft_cannot_be_step_recipe(self):
        for kind, doc in (("step", NATIVE), ("native", STEP),
                          ("step", dict(STEP, id="../escape"))):
            code, _ = self.request("POST", "/api/save", {"kind": kind, "recipe": doc})
            self.assertEqual(code, 422)
        self.assertFalse((Path(self.temp.name) / "steps" / "escape").exists())

    def test_static_resources_fixed_allowlist(self):
        status, data = self.request("GET", "/studio")
        self.assertEqual(status, 200)
        self.assertIn("Конструктор".encode("utf-8"), data)
        status, _ = self.request("GET", "/../../.env.secrets")
        self.assertEqual(status, 404)
        status, _ = self.request("GET", "/studio-config.js", host=False)
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/studio-config.js")
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/studio-config.js", extra_headers={
            "Sec-Fetch-Site": "cross-site", "Referer": "http://attacker.invalid/"})
        self.assertEqual(status, 403)
        status, payload = self.request("GET", "/studio-config.js", extra_headers={
            "Sec-Fetch-Site": "same-origin", "Referer": self.server.origin + "/studio"})
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode("ascii"), payload)

    def test_no_production_endpoint(self):
        for path in ("/api/start", "/api/output", "/api/stop", "/api/firmware"):
            status, _ = self.request("POST", path, {"kind": "step", "recipe": STEP})
            self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
