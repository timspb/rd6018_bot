"""Phase 5.3 interface contracts; no adapter implementation or I/O."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from application.rd_transport import (
    ControlProvider,
    ESPDirectRDAdapter,
    HARDAdapter,
    RDTransport,
    TelemetryProvider,
)


ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    ROOT / "docs" / "RD6018_INTERFACE_BOUNDARY_MODEL.md",
    ROOT / "docs" / "RD6018_RD_TRANSPORT_CONTRACT.md",
)


class InterfaceBoundaryTests(unittest.TestCase):
    def test_transport_contract_has_read_and_control_surfaces(self) -> None:
        for contract in (RDTransport, HARDAdapter, ESPDirectRDAdapter):
            for name in ("read_telemetry", "read_output_state", "read_readback", "set_voltage", "set_current", "output_on", "output_off"):
                self.assertTrue(hasattr(contract, name), (contract, name))

    def test_telemetry_and_control_are_separate_contracts(self) -> None:
        telemetry_names = {"read_telemetry", "read_output_state", "read_readback"}
        control_names = {"set_voltage", "set_current", "output_on", "output_off"}
        self.assertTrue(telemetry_names.issubset(set(TelemetryProvider.__dict__)))
        self.assertTrue(control_names.issubset(set(ControlProvider.__dict__)))
        self.assertTrue(telemetry_names.isdisjoint(control_names))

    def test_interface_documents_define_isolation_and_adapter_boundaries(self) -> None:
        text = "\n".join(path.read_text(encoding="utf-8") for path in DOCS)
        for term in ("UI Module", "Telemetry Boundary", "Control Boundary", "HARDAdapter", "ESPDirectRDAdapter", "physical execution"):
            self.assertIn(term, text)
        self.assertIn("must not own or import", text)

    def test_ui_application_has_no_infrastructure_imports(self) -> None:
        forbidden = ("hass_api", "homeassistant", "esphome", "runtime.physical", "serial", "modbus")
        ui_files = tuple((ROOT / "application").glob("operator_*.py"))
        violations: list[str] = []
        for path in ui_files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if any(token in name.lower() for token in forbidden):
                        violations.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual([], violations)

    def test_domain_has_no_interface_or_transport_imports(self) -> None:
        forbidden = ("rd_transport", "hass_api", "homeassistant", "esphome", "runtime.physical", "serial", "modbus")
        violations: list[str] = []
        for path in (ROOT / "runtime" / "charge").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if any(token in name.lower() for token in forbidden):
                        violations.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
