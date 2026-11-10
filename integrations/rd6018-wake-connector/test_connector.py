import json
import tempfile
import unittest
from pathlib import Path

from connector import Event, Outbox, deliver_ready, load_config, normalize_snapshot, validate_route
from connector_service import read_snapshot


NOW = 1794300000.0
ROUTE = "a" * 32


class ConnectorTests(unittest.TestCase):
    def test_route_shape_and_rotation_are_external(self):
        self.assertEqual(validate_route(ROUTE), ROUTE)
        for value in (None, "", "A" * 32, "b" * 31, ROUTE + "x"):
            with self.assertRaises(ValueError):
                validate_route(value)

    def test_normalization_transitions_and_secret_allowlist(self):
        old = {"stage": "MAIN", "fault_code": None, "guard_state": "ok", "stale": False}
        raw = {"schema": 1, "captured_at": NOW,
               "state": {"source": "esp_native_api", "values": {
                   "stage": "MIX", "voltage_v": 15.1, "current_a": 2.2,
                   "temperature_c": 24, "freshness_s": 2,
                   "password": "never", "route": ROUTE, "private_note": "omit"}}}
        events, state = normalize_snapshot(raw, old, NOW + 1)
        self.assertEqual([e.kind for e in events], ["stage_transition"])
        self.assertEqual(events[0].fields["voltage_v"], 15.1)
        self.assertNotIn("password", events[0].fields)
        self.assertNotIn("route", events[0].fields)
        self.assertNotIn("private_note", events[0].fields)
        self.assertEqual(state["stage"], "MIX")

    def test_rejects_stale_or_untyped_source(self):
        raw = {"schema": 1, "captured_at": NOW - 301,
               "state": {"source": "esp_native_api", "values": {"stage": "MAIN"}}}
        with self.assertRaises(ValueError):
            normalize_snapshot(raw, None, NOW)
        raw["captured_at"] = NOW
        raw["state"]["source"] = "made_up"
        with self.assertRaises(ValueError):
            normalize_snapshot(raw, None, NOW)

    def test_dedup_restart_retry_and_bounded_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outbox.sqlite3"
            first = Event.create("fault_alarm", "OVERTEMP", NOW, "rd6018_readonly_diagnostic",
                                 {"fault_code": "OVERTEMP"}, "critical")
            box = Outbox(path, max_events=1, max_age_s=1000)
            self.assertTrue(box.enqueue(first, NOW))
            self.assertFalse(box.enqueue(first, NOW))
            second = Event.create("fault_alarm", "OVERCURRENT", NOW, "rd6018_readonly_diagnostic",
                                  {"fault_code": "OVERCURRENT"})
            self.assertFalse(box.enqueue(second, NOW))
            box.retry_later(first.event_id, 1, NOW)
            self.assertEqual(box.pending(NOW + 1), [])
            box.close()
            box = Outbox(path, max_events=1, max_age_s=1000)
            self.assertEqual(len(box.pending(NOW + 10)), 1)
            box.close()

    def test_invalid_route_or_missing_transport_holds_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Outbox(Path(tmp) / "queue.db")
            event = Event.create("heartbeat", "periodic", NOW, "connector_timer", {})
            box.enqueue(event, NOW)
            self.assertEqual(deliver_ready(box, None, lambda *_: "acknowledged", NOW), 0)
            self.assertEqual(deliver_ready(box, "bad-route", lambda *_: "acknowledged", NOW), 0)
            self.assertEqual(deliver_ready(box, ROUTE, None, NOW), 0)
            self.assertEqual(len(box.pending(NOW)), 1)
            box.close()

    def test_delivery_states_are_not_conflated(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Outbox(Path(tmp) / "queue.db")
            event = Event.create("heartbeat", "periodic", NOW, "connector_timer", {})
            box.enqueue(event, NOW)
            self.assertEqual(deliver_ready(box, ROUTE, lambda *_: "submitted", NOW), 1)
            row = box.db.execute("select state from events").fetchone()
            self.assertEqual(row[0], "submitted")
            box.close()

    def test_config_permissions_and_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"schema": 1, "route": None}))
            path.chmod(0o600)
            self.assertEqual(load_config(path)["poll_interval_s"], 30)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                load_config(path)

    def test_snapshot_file_refuses_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.write_text("{}")
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                read_snapshot(link)
            big = root / "big"
            big.write_text(" " * 65537)
            with self.assertRaises(ValueError):
                read_snapshot(big)


if __name__ == "__main__":
    unittest.main()
