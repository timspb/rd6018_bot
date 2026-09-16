"""Phase 8.3 UI adapter boundary tests; shadow only."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from application.intents import OperatorIntentKind
from application.ui_adapter import OperatorUIAdapter


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "ui_adapter.py"


class UIAdapterBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = OperatorUIAdapter()

    def test_commands_create_operator_intents(self) -> None:
        cases = {
            "START AGM 72": (OperatorIntentKind.START_CHARGE, {"profile": "AGM", "capacity_ah": 72.0}),
            "STOP": (OperatorIntentKind.STOP_CHARGE, {}),
            "PAUSE": (OperatorIntentKind.PAUSE_CHARGE, {}),
            "RESUME": (OperatorIntentKind.RESUME_CHARGE, {}),
            "STATUS": (OperatorIntentKind.REFRESH_PANEL, {}),
        }
        for command, (kind, parameters) in cases.items():
            with self.subTest(command=command):
                result = self.adapter.parse(command, user="operator", trace_id="trace-ui")
                self.assertTrue(result.accepted)
                self.assertEqual(kind, result.intent.kind)
                self.assertEqual(parameters, dict(result.intent.parameters))
                self.assertEqual("trace-ui", result.trace_id)
                self.assertEqual("trace-ui", result.diagnostic.correlation.trace_id)

    def test_invalid_command_rejected_without_intent(self) -> None:
        for command in ("", "START", "START AGM nope", "STOP now", "UNKNOWN"):
            with self.subTest(command=command):
                result = self.adapter.parse(command, user="operator", trace_id="trace-invalid")
                self.assertFalse(result.accepted)
                self.assertIsNone(result.intent)
                self.assertEqual("trace-invalid", result.diagnostic.correlation.trace_id)

    def test_ui_module_has_no_domain_or_infrastructure_imports(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ("runtime.charge", "charge_engine", "session_manager", "safety", "controller", "hass", "esphome", "transport", "telegram", "physical")
        self.assertEqual([], [name for name in imports if any(item in name for item in forbidden)])

    def test_ui_document_records_boundary(self) -> None:
        text = (ROOT / "docs" / "RD6018_UI_BOUNDARY_MODEL.md").read_text(encoding="utf-8")
        for phrase in ("OperatorUIAdapter", "OperatorIntent", "START", "STOP", "PAUSE", "RESUME", "STATUS", "physical execution"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
