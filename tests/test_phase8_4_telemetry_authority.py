"""Phase 8.4 read-only telemetry adapter tests."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import unittest

from application.telemetry_authority import (
    ESPDirectTelemetryAdapter,
    HATelemetryAdapter,
    TelemetryArbitrator,
    TelemetrySource,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "telemetry_authority.py"


class TelemetryAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_esp_telemetry_mapping(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
        adapter = ESPDirectTelemetryAdapter(
            lambda: {"timestamp": now, "voltage": "14.2", "current": 2, "temperature": 23, "output_state": True},
            clock=lambda: now,
        )
        snapshot = await adapter.read()
        self.assertEqual(TelemetrySource.ESP_DIRECT, snapshot.source)
        self.assertEqual(28.4, snapshot.power)
        self.assertTrue(snapshot.is_fresh)
        self.assertEqual(1.0, snapshot.confidence)

    async def test_ha_telemetry_mapping(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
        adapter = HATelemetryAdapter(
            lambda: {"captured_at": now, "measured_voltage": 13.8, "measured_current": 1.5, "temp": 24, "output_state": False},
            clock=lambda: now,
        )
        snapshot = await adapter.read()
        self.assertEqual(TelemetrySource.HA, snapshot.source)
        self.assertAlmostEqual(20.7, snapshot.power)
        self.assertEqual(0.0, snapshot.freshness_s)

    async def test_arbitration_priority_and_stale_handling(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        esp = await ESPDirectTelemetryAdapter(lambda: {"timestamp": now.timestamp(), "voltage": 14}, clock=lambda: now.timestamp()).read()
        ha = await HATelemetryAdapter(lambda: {"timestamp": now.timestamp(), "voltage": 13}, clock=lambda: now.timestamp()).read()
        arbitrator = TelemetryArbitrator()
        self.assertEqual(TelemetrySource.ESP_DIRECT, arbitrator.select(esp_direct=esp, ha=ha, now=now).source)

        stale = await ESPDirectTelemetryAdapter(lambda: {"timestamp": (now.timestamp() - 100), "voltage": 15}, max_age_s=10, clock=lambda: now.timestamp()).read()
        selected = arbitrator.select(esp_direct=stale, ha=ha, now=now)
        self.assertEqual(TelemetrySource.HA, selected.source)
        selected = arbitrator.select(esp_direct=stale, ha=None, now=now)
        self.assertEqual(TelemetrySource.LAST_KNOWN, selected.source)
        selected = TelemetryArbitrator().select(esp_direct=stale, ha=None, now=now)
        self.assertEqual(TelemetrySource.UNKNOWN, selected.source)

    def test_no_control_calls_or_source_clients(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        forbidden_imports = ("ha", "esp", "telegram", "controller", "safety", "physical", "transport")
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        self.assertEqual([], [name for name in imports if any(item in name for item in forbidden_imports)])
        text = MODULE.read_text(encoding="utf-8").lower()
        for call in ("output_on", "output_off", "set_voltage", "set_current", "write("):
            self.assertNotIn(call, text)

    def test_document_declares_read_only_authority(self) -> None:
        text = (ROOT / "docs" / "RD6018_TELEMETRY_AUTHORITY_MODEL.md").read_text(encoding="utf-8")
        for phrase in ("HATelemetryAdapter", "ESPDirectTelemetryAdapter", "last known", "unknown", "read-only"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
