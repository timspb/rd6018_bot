"""Phase 11.0 staged telemetry ownership tests."""

from datetime import datetime, timezone
from pathlib import Path
import unittest

from application.telemetry_authority import ESPDirectTelemetryAdapter, HATelemetryAdapter, TelemetrySource
from application.telemetry_ownership import TelemetryOwnershipCoordinator, TelemetryOwnershipState, TelemetryParityState


ROOT = Path(__file__).resolve().parents[1]


class TelemetryOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_ownership_state_and_source_arbitration(self) -> None:
        now = datetime.now(timezone.utc)
        epoch = now.timestamp()
        esp = await ESPDirectTelemetryAdapter(lambda: {"timestamp": epoch, "voltage": 14.2, "current": 2.0}, clock=lambda: epoch).read()
        ha = await HATelemetryAdapter(lambda: {"timestamp": epoch, "voltage": 14.0, "current": 1.8}, clock=lambda: epoch).read()
        coordinator = TelemetryOwnershipCoordinator()
        self.assertEqual(TelemetryOwnershipState.V2_PRIMARY, coordinator.state)
        view = coordinator.stage(trace_id="trace-11", v2_snapshot=esp, esp_direct=esp, ha=ha, now=now)
        self.assertEqual(TelemetryOwnershipState.V3_STAGED, view.state)
        self.assertEqual(TelemetrySource.ESP_DIRECT, view.snapshot.source)
        self.assertEqual(TelemetryParityState.EQUAL, view.parity.state)

    async def test_telemetry_parity_and_shadow_evidence(self) -> None:
        now = datetime.now(timezone.utc)
        epoch = now.timestamp()
        v2 = await HATelemetryAdapter(lambda: {"timestamp": epoch, "voltage": 13.8}, clock=lambda: epoch).read()
        esp = await ESPDirectTelemetryAdapter(lambda: {"timestamp": epoch, "voltage": 14.2}, clock=lambda: epoch).read()
        coordinator = TelemetryOwnershipCoordinator()
        view = coordinator.stage(trace_id="trace-diff", v2_snapshot=v2, esp_direct=esp, ha=None, now=now)
        self.assertEqual(TelemetryParityState.DIFFERENT, view.parity.state)
        self.assertEqual(14.2, view.parity.differences["voltage"]["v3"])
        self.assertEqual((view,), coordinator.shadow_evidence)

    async def test_rollback_to_v2_telemetry(self) -> None:
        now = datetime.now(timezone.utc)
        epoch = now.timestamp()
        v2 = await HATelemetryAdapter(lambda: {"timestamp": epoch, "voltage": 13.8}, clock=lambda: epoch).read()
        esp = await ESPDirectTelemetryAdapter(lambda: {"timestamp": epoch, "voltage": 14.2}, clock=lambda: epoch).read()
        coordinator = TelemetryOwnershipCoordinator()
        coordinator.stage(trace_id="trace-rb", v2_snapshot=v2, esp_direct=esp, ha=None, now=now)
        rollback = coordinator.rollback_to_v2(trace_id="trace-rb-2", now=now)
        self.assertEqual(TelemetryOwnershipState.V2_ROLLBACK, rollback.state)
        self.assertIs(v2, coordinator.canonical())
        self.assertEqual(TelemetryParityState.EQUAL, rollback.parity.state)

    def test_no_control_path(self) -> None:
        source = (ROOT / "application" / "telemetry_ownership.py").read_text(encoding="utf-8").lower()
        for token in ("output_on(", "output_off(", "set_voltage(", "set_current(", "controller.start", "controller.stop", "ha.write", "esp.write"):
            self.assertNotIn(token, source)

    def test_document_declares_staged_telemetry_only(self) -> None:
        text = (ROOT / "docs" / "RD6018_TELEMETRY_OWNERSHIP_MIGRATION.md").read_text(encoding="utf-8")
        for phrase in ("V2", "V3 staged", "ESP Direct", "HA", "Rollback", "no control"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
