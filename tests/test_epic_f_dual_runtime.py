"""EPIC F dual-runtime coexistence tests; no control or physical integration."""

import ast
from pathlib import Path
import unittest

from application.dual_runtime import DualRuntimeCoordinator, RuntimeHealthSnapshot
from application.runtime_composition import RuntimeLifecycle, V3RuntimeComposition


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "dual_runtime.py"
DOC = ROOT / "docs" / "RD6018_DUAL_RUNTIME_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


def v2_health(*, alive=True, healthy=True):
    return RuntimeHealthSnapshot(
        runtime="V2", alive=alive, healthy=healthy, execution_owner=True,
        shadow_healthy=False, no_execution_authority=False, lifecycle="running",
        persistence_namespace="v2-production", diagnostics_namespace="v2-production-diagnostics",
    )


class EpicFDualRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_dual_startup_and_health_ownership(self) -> None:
        v2_calls = []
        runtime = V3RuntimeComposition()
        coordinator = DualRuntimeCoordinator(runtime, lambda: (v2_calls.append("health") or v2_health()))
        health = await coordinator.start()
        self.assertEqual(RuntimeLifecycle.RUNNING.value, health.v3.lifecycle)
        self.assertTrue(health.v2.execution_owner)
        self.assertFalse(health.v3.execution_owner)
        self.assertTrue(health.v3.no_execution_authority)
        self.assertTrue(health.isolated)
        self.assertGreaterEqual(len(v2_calls), 1)
        await coordinator.shutdown()

    async def test_shutdown_isolation_does_not_control_v2(self) -> None:
        calls = []
        coordinator = DualRuntimeCoordinator(V3RuntimeComposition(), lambda: v2_health())
        await coordinator.start()
        await coordinator.shutdown()
        self.assertEqual(RuntimeLifecycle.STOPPED.value, coordinator.health().v3.lifecycle)
        self.assertEqual([], calls)

    async def test_v2_health_and_namespace_validation(self) -> None:
        with self.assertRaises(RuntimeError):
            await DualRuntimeCoordinator(V3RuntimeComposition(), lambda: v2_health(alive=False)).start()
        with self.assertRaises(ValueError):
            DualRuntimeCoordinator(V3RuntimeComposition(), lambda: v2_health(), v3_persistence_namespace="same", v3_diagnostics_namespace="same")

    def test_no_duplicate_physical_path_or_production_imports(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ("bot", "telegram", "homeassistant", "esphome", "hass", "rd_transport", "runtime.physical", "runtime.output", "controller")
        self.assertEqual([], [name for name in imports if any(token in name for token in forbidden)])
        source = MODULE.read_text(encoding="utf-8")
        for token in ("output_on(", "output_off(", "set_voltage(", "set_current(", "turn_on(", "turn_off(", "renew"):
            self.assertNotIn(token, source)

    def test_document_and_canonical_state(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for term in ("Lifecycle isolation", "Resource isolation", "Duplicate ownership risks", "RuntimeHealthSnapshot", "V3 crash", "V2 crash", "DUAL_RUNTIME_SHADOW_READY", "NOT_READY_FOR_CUTOVER"):
            self.assertIn(term, text)
        canonical = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("### EPIC F — Dual runtime operation", canonical)
        self.assertIn("Current status: dual-runtime shadow coexistence", canonical)


if __name__ == "__main__":
    unittest.main()
