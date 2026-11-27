import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.charge.persistence import begin_start_pending
from runtime.startup_recovery import StartupRecovery


class _Guard:
    def __init__(self):
        self.quarantined = False
        self.reason = None

    def quarantine(self, reason):
        self.quarantined = True
        self.reason = reason

    def may_run_automatic_control(self):
        return not self.quarantined


class _Port:
    def __init__(self, receipt):
        self.receipt = receipt
        self.session_recovery_guard = _Guard()
        self.off_calls = 0

    async def request_emergency_off_receipt(self):
        self.off_calls += 1
        return self.receipt


class _StartupPendingTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_pending_keeps_startup_recovery_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "charge_session.json"
            path.write_text('{"stage":"IDLE"}', encoding="utf-8")
            port = _Port(None)
            app = SimpleNamespace(hass=object())
            recovery = StartupRecovery(app, object(), object())
            with patch("runtime.startup_recovery.SESSION_FILE", path), \
                 patch("runtime.startup_recovery.get_or_create_execution_port", return_value=port):
                self.assertTrue(await recovery._settle_start_pending_before_restore())
            self.assertEqual(port.off_calls, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"stage":"IDLE"}')

    async def test_valid_pending_requires_receipt_then_later_same_generation_native_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "charge_session.json"
            prior = {"stage": "IDLE", "profile": "EFB"}
            path.write_text(json.dumps(prior), encoding="utf-8")
            pending = begin_start_pending({"stage": "PREP"}, transaction_id="tx-1", path=path)
            self.assertEqual(pending.status.value, "COMMITTED")
            receipt = SimpleNamespace(
                requested_target=False, terminal_status="APPLIED", observed_r18=0,
                terminal_completed_monotonic=time.monotonic(), connection_generation=7,
            )
            port = _Port(receipt)
            app = SimpleNamespace(hass=SimpleNamespace(
                get_native_physical_output_report=lambda: None,
            ))
            async def report():
                return 0, {"status": "ok", "native_type": "SensorState",
                           "connection_generation": 7,
                           "subscription_timestamp_monotonic": time.monotonic()}
            app.hass.get_native_physical_output_report = report
            recovery = StartupRecovery(app, object(), object())
            with patch("runtime.startup_recovery.SESSION_FILE", path), \
                 patch("runtime.startup_recovery.get_or_create_execution_port", return_value=port):
                self.assertTrue(await recovery._settle_start_pending_before_restore())
            self.assertEqual(port.off_calls, 1)
            self.assertEqual(path.read_text(encoding="utf-8"), json.dumps(prior))

    async def test_periodic_r18_callback_after_off_receipt_settles_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "charge_session.json"
            prior = b'{"stage":"IDLE","start_transaction_generation":0}'
            path.write_bytes(prior)
            begin_start_pending({"stage": "PREP"}, transaction_id="r18-periodic", path=path)
            receipt_at = time.monotonic()
            receipt = SimpleNamespace(
                requested_target=False, terminal_status="APPLIED", observed_r18=0,
                terminal_completed_monotonic=receipt_at, connection_generation=7,
            )
            port = _Port(receipt)
            samples = iter((receipt_at - 1.0, receipt_at, None))
            seen = []
            async def report():
                sample = next(samples)
                stamp = time.monotonic() if sample is None else sample
                seen.append(stamp)
                return 0.0, {"status": "ok", "native_type": "SensorState",
                             "connection_generation": 7,
                             "subscription_timestamp_monotonic": stamp}
            app = SimpleNamespace(hass=SimpleNamespace(get_native_physical_output_report=report))
            recovery = StartupRecovery(app, object(), object())
            with patch("runtime.startup_recovery.SESSION_FILE", path), \
                 patch("runtime.startup_recovery.get_or_create_execution_port", return_value=port):
                self.assertTrue(await recovery._settle_start_pending_before_restore())
            self.assertEqual(len(seen), 3)
            self.assertEqual(port.off_calls, 1)
            self.assertEqual(path.read_bytes(), prior)

    async def test_stale_native_report_quarantines_and_preserves_pending_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "charge_session.json"
            path.write_text('{"stage":"IDLE"}', encoding="utf-8")
            pending = begin_start_pending({"stage": "PREP"}, transaction_id="tx-2", path=path)
            before = path.read_bytes()
            receipt = SimpleNamespace(
                requested_target=False, terminal_status="APPLIED", observed_r18=0,
                terminal_completed_monotonic=20.0, connection_generation=7,
            )
            port = _Port(receipt)
            async def report():
                return 0, {"status": "ok", "native_type": "SensorState",
                           "connection_generation": 7,
                           "subscription_timestamp_monotonic": 20.0}
            app = SimpleNamespace(hass=SimpleNamespace(get_native_physical_output_report=report))
            recovery = StartupRecovery(app, object(), object())
            with patch("runtime.startup_recovery.SESSION_FILE", path), \
                 patch("runtime.startup_recovery.get_or_create_execution_port", return_value=port):
                self.assertFalse(await recovery._settle_start_pending_before_restore())
            self.assertTrue(port.session_recovery_guard.quarantined)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(port.off_calls, 1)


if __name__ == "__main__":
    unittest.main()
