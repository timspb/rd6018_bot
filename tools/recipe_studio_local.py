#!/usr/bin/env python3
"""Recipe Studio local-only browser bridge; no device imports or START endpoints.

Started explicitly by the PC operator and bound only to 127.0.0.1.
All save operations reuse the existing immutable libraries and validators.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import secrets
import sys
from threading import Lock
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import MAX_MANUAL_VOLTAGE
from runtime.safety.variables import MAX_STAGE_CURRENT_A
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.recipe_studio_history import (
    history, load_document, compare, archive,
)
from runtime.charge.programs.recipe_studio_import import (
    inspect_step_document, inspect_native_document,
    publish_step_document, publish_native_document,
)

ASSETS = {
    "/studio": ("recipe_visual_editor_prototype.html", "text/html; charset=utf-8"),
    "/recipe_studio_native_catalog.js": ("recipe_studio_native_catalog.js", "application/javascript"),
    "/recipe_studio_native_editor.js": ("recipe_studio_native_editor.js", "application/javascript"),
    "/recipe_studio_save.js": ("recipe_studio_save.js", "application/javascript"),
    "/recipe_studio_history.js": ("recipe_studio_history.js", "application/javascript"),
}
MAX_BYTES = 256 * 1024


class StudioHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], library_root: Path):
        super().__init__(address, StudioHandler)
        self.root = library_root.resolve()
        self.token = secrets.token_urlsafe(32)
        self.lock = Lock()
        self.assets_root = Path(__file__).resolve().parent

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def store(self, kind: str):
        if kind == "native":
            return NativeRecipeDraftLibrary(self.root / "native")
        if kind == "step":
            return RecipeLibrary(
                self.root / "steps",
                max_voltage_v=float(MAX_MANUAL_VOLTAGE),
                max_current_a=float(MAX_STAGE_CURRENT_A.default),
            )
        raise ValueError("unsupported recipe kind")

    def library_operation(self, payload: dict, operation: str) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"kind", "id", "version", "left", "right"}:
            raise ValueError("invalid history request")
        kind = payload.get("kind")
        with self.lock:
            library = self.store(kind)
            if operation == "list":
                if set(payload) != {"kind"}:
                    raise ValueError("invalid list request")
                return {"items": history(library, kind), "physical_start_authorized": False}
            name = payload.get("id")
            if operation == "load":
                if set(payload) != {"kind", "id", "version"}:
                    raise ValueError("invalid load request")
                return {"recipe": load_document(library, kind, name, payload.get("version")),
                        "physical_start_authorized": False}
            if operation == "compare":
                if set(payload) != {"kind", "id", "left", "right"}:
                    raise ValueError("invalid compare request")
                return {**compare(library, kind, name, payload.get("left"), payload.get("right")),
                        "physical_start_authorized": False}
            if operation == "archive":
                if set(payload) != {"kind", "id"}:
                    raise ValueError("invalid archive request")
                return {**archive(library, kind, name), "physical_start_authorized": False}
            raise ValueError("invalid library operation")

    def apply(self, kind: str, document: dict, save: bool) -> dict:
        library = self.store(kind)
        with self.lock:
            if kind == "native":
                result = (
                    publish_native_document(library, document)
                    if save else inspect_native_document(document)
                )
                # Source-of-truth readback after a successful immutable save.
                if save and library.load(result.name, result.version) != result.draft:
                    raise ValueError("saved native draft readback mismatch")
                return {
                    "status": "SAVED" if save else "VALIDATED",
                    "kind": kind, "id": result.name, "version": result.version,
                    "base_recipe_id": result.draft.base_recipe_id,
                    "physical_start_authorized": False,
                }
            result = (
                publish_step_document(library, document)
                if save else inspect_step_document(
                    document, max_voltage_v=library.max_voltage_v,
                    max_current_a=library.max_current_a,
                )
            )
            if save and library.load(result.recipe.recipe_id, result.recipe.version).digest != result.recipe.digest:
                raise ValueError("saved step recipe readback mismatch")
            return {
                "status": "SAVED" if save else "VALIDATED",
                "kind": kind, "id": result.recipe.recipe_id,
                "version": result.recipe.version, "digest": result.recipe.digest,
                "start_eligible_structure": result.start_eligible,
                "warnings": result.warnings, "physical_start_authorized": False,
            }


class StudioHandler(BaseHTTPRequestHandler):
    server: StudioHTTPServer

    def log_message(self, format: str, *args) -> None:
        # Do not log URL query strings, request bodies, or capability tokens.
        return

    def _send(self, code: int, payload: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", (
            "default-src 'none'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self' data:; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'"
        ))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj: dict):
        self._send(status, json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _host_ok(self):
        return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "invalid host"})
        path = urlparse(self.path).path
        if path == "/studio-config.js":
            # A foreign web page can otherwise include this URL via <script> and
            # read the capability despite CORS. Require a same-origin script fetch.
            if (self.headers.get("Sec-Fetch-Site") != "same-origin"
                    or self.headers.get("Referer") != self.server.origin + "/studio"):
                return self._json(403, {"error": "editor context required"})
            config = {"origin": self.server.origin, "token": self.server.token}
            script = "window.RD6018_STUDIO_CONFIG = " + json.dumps(config) + ";\n"
            return self._send(200, script.encode("utf-8"), "application/javascript")
        asset = ASSETS.get(path)
        if asset is None:
            return self._json(404, {"error": "not found"})
        filename, content_type = asset
        return self._send(200, (self.server.assets_root / filename).read_bytes(), content_type)

    def do_POST(self):
        if not self._host_ok() or self.headers.get("Origin") != self.server.origin:
            return self._json(403, {"error": "invalid origin"})
        token = self.headers.get("X-Recipe-Studio-Token", "")
        if not hmac.compare_digest(token, self.server.token):
            return self._json(403, {"error": "invalid editor capability"})
        if self.headers.get("Content-Type") != "application/json":
            return self._json(415, {"error": "application/json required"})
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if size < 1 or size > MAX_BYTES:
            return self._json(413, {"error": "request size invalid"})
        parts = urlparse(self.path)
        operations = {"/api/list": "list", "/api/load": "load",
                      "/api/compare": "compare", "/api/archive": "archive"}
        if parts.path not in ("/api/check", "/api/save", *operations) or parts.query:
            return self._json(404, {"error": "not found"})
        try:
            document = json.loads(
                self.rfile.read(size).decode("utf-8"),
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError("nonfinite JSON constant: " + value)),
            )
            if parts.path in operations:
                result = self.server.library_operation(document, operations[parts.path])
            else:
                if not isinstance(document, dict) or set(document) != {"kind", "recipe"}:
                    raise ValueError("request must contain only kind and recipe")
                if not isinstance(document["recipe"], dict):
                    raise ValueError("recipe must be a JSON object")
                result = self.server.apply(
                    document["kind"], document["recipe"], save=parts.path == "/api/save",
                )
            return self._json(200, result)
        except (ValueError, TypeError, OSError, FileExistsError, KeyError) as exc:
            return self._json(422, {"error": str(exc)[:600]})

    def do_OPTIONS(self):
        self._json(405, {"error": "cross-origin requests are not supported"})


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Local RD6018 recipe editor bridge (no hardware)")
    parser.add_argument("--library-root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port is outside range")
    root = args.library_root.resolve()
    if any(p.lower() in {"state", "production", "node104"} for p in root.parts):
        parser.error("select an isolated non-production library, not node104/state")
    with StudioHTTPServer(("127.0.0.1", args.port), root) as server:
        print(f"RECIPE_STUDIO_LOCAL_ONLY {server.origin}/studio", flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
