"""EPIC E V3 runtime shell tests; no production or physical integration."""

import asyncio
import ast
from pathlib import Path
import time
import unittest

from application.runtime_composition import RuntimeLifecycle, V3RuntimeComposition


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "runtime_composition.py"
DOC = ROOT / "docs" / "RD6018_RUNTIME_MIGRATION_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


class EpicERuntimeMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_and_health_are_shadow_only(self) -> None:
        runtime = V3RuntimeComposition()
        health = await runtime.start()
        self.assertEqual(RuntimeLifecycle.RUNNING, health.state)
        self.assertTrue(health.dependencies_ready)
        self.assertTrue(health.shadow_only)
        self.assertFalse(health.physical_execution_enabled)
        self.assertTrue(health.diagnostics_ready)
        await runtime.shutdown()

    async def test_dependency_graph_and_shadow_processing(self) -> None:
        now = time.time()
        runtime = V3RuntimeComposition(
            composition=__import__("application.shadow_composition", fromlist=["ApplicationComposition"]).ApplicationComposition.shadow(
                esp_reader=lambda: {"timestamp": now, "voltage": 14.1, "current": 1.0, "temperature": 23},
                ha_reader=lambda: {"timestamp": now, "voltage": 13.9, "current": 1.0, "temperature": 24},
            ),
            shadow_observer=object(),
        )
        health = await runtime.start()
        self.assertTrue(health.shadow_observer_connected)
        result = await runtime.process_shadow("START AGM 70", user="test", trace_id="epic-e")
        self.assertTrue(result.accepted)
        await runtime.shutdown()

    async def test_shutdown_cancels_background_workers(self) -> None:
        cancelled = asyncio.Event()

        async def worker(_runtime):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        runtime = V3RuntimeComposition(workers=(worker,))
        await runtime.start()
        await asyncio.sleep(0)
        self.assertEqual(1, runtime.health().workers_running)
        health = await runtime.shutdown()
        self.assertEqual(RuntimeLifecycle.STOPPED, health.state)
        self.assertTrue(cancelled.is_set())

    def test_no_production_or_physical_imports(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ("bot", "telegram", "homeassistant", "esphome", "hass", "rd_transport", "runtime.physical", "runtime.output")
        self.assertEqual([], [name for name in imports if any(item in name for item in forbidden)])
        source = MODULE.read_text(encoding="utf-8")
        for token in ("output_on(", "output_off(", "set_voltage(", "set_current(", "turn_on(", "turn_off("):
            self.assertNotIn(token, source)

    def test_document_and_canonical_status(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for term in ("startup lifecycle", "shutdown lifecycle", "background shadow workers", "health reporting", "SHADOW_RUNTIME_READY", "NOT_READY_FOR_CUTOVER"):
            self.assertIn(term, text)
        canonical = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("### EPIC E — Runtime cutover", canonical)
        self.assertIn("Current status: runtime composition shadow shell", canonical)
        self.assertIn("V2 remains the runtime and physical owner", canonical)


if __name__ == "__main__":
    unittest.main()
