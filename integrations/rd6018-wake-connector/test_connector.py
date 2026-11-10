import json
import os
import tempfile
import unittest
import uuid
import ssl
from pathlib import Path

from connector import (EVENT_TYPES, SOURCE, EventEnvelope, EventGatewayClient,
                       GatewayAcceptance, Outbox, UnwiredEventGatewayClient, load_config, normalize_snapshot)
from ha_source import HAConfig, HAReadOnlyClient, SourceError, SourceSnapshot, load_entity_allowlist

NOW = 1794300000.0


class FakeGateway:
    def __init__(self, result):
        self.result = result
        self.events = []

    def submit(self, event):
        self.events.append(event)
        return self.result


class ConnectorTests(unittest.TestCase):
    def test_universal_envelope_shape_and_deterministic_uuid(self):
        event = EventEnvelope.for_occurrence("charger.fault", "fault-1", NOW,
                                             {"fault_code": "OVERTEMP"}, "critical")
        self.assertEqual(set(event.to_dict()), {"event_id", "source", "event_type", "severity", "occurred_at", "payload", "schema_version"})
        self.assertEqual(event.source, "rd6018-node104")
        self.assertEqual(uuid.UUID(event.event_id).version, 5)
        self.assertEqual(event.to_dict()["occurred_at"], "2026-11-10T08:40:00Z")
        self.assertEqual(event.event_id, EventEnvelope.for_occurrence("charger.fault", "fault-1", NOW + 10, {"fault_code": "OVERTEMP"}, "critical").event_id)
        self.assertNotEqual(event.event_id, EventEnvelope.for_occurrence("charger.fault", "fault-2", NOW, {}, "critical").event_id)

    def test_strict_envelope_validation_and_payload_allowlist(self):
        event = EventEnvelope.for_occurrence("charger.heartbeat", "slot-1", NOW,
                                             {"temperature_internal_c": 35.2,
                                              "temperature_external_c": 30.0,
                                              "token": "secret", "raw_log": "omit"})
        self.assertEqual(event.payload, {"temperature_internal_c": 35.2, "temperature_external_c": 30.0})
        base = event.to_dict()
        for changes in ({"event_id": "not-uuid"}, {"source": "other"},
                        {"event_type": "codex.completed"}, {"severity": "debug"},
                        {"occurred_at": "2026-11-10T14:00:00+00:00"},
                        {"schema_version": 2}, {"payload": {"token": "secret"}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                EventEnvelope(**(base | changes))
        self.assertEqual(EVENT_TYPES, frozenset({
            "charger.fault", "charger.stage_changed", "charger.mode_changed", "charger.guard_recovered",
            "charger.telemetry_stale", "charger.telemetry_unknown", "charger.telemetry_recovered", "charger.guard_fault",
            "charger.service_down", "charger.service_recovered", "charger.heartbeat",
            }))

    def test_normalization_emits_rd6018_semantics_and_filters_payload(self):
        old = {"stage": "MAIN", "fault_code": None, "guard_state": "ok", "stale": False}
        raw = SourceSnapshot._from_adapter(NOW, {
                   "stage": "MIX", "voltage_v": 15.1, "current_a": 2.2,
                   "temperature_internal_c": 24, "temperature_external_c": 29,
                   "freshness_s": 2, "freshness_known": True,
                   "password": "never", "session_id": "omit"}, True, 2)
        events, state = normalize_snapshot(raw, old, NOW + 1)
        self.assertEqual([e.event_type for e in events], ["charger.stage_changed"])
        self.assertEqual(events[0].payload["voltage_v"], 15.1)
        self.assertEqual(events[0].payload["temperature_internal_c"], 24)
        self.assertEqual(events[0].payload["temperature_external_c"], 29)
        self.assertNotIn("password", events[0].payload)
        self.assertNotIn("session_id", events[0].payload)
        self.assertEqual(state["stage"], "MIX")

    def test_stage_occurrence_identity_survives_capture_time_changes(self):
        previous = {"stage": "Main Charge", "fault_code": None, "guard_state": "ok",
                    "stale": False, "freshness_unknown": False}
        values = {"stage": "Mix Mode", "stage_occurrence_at": NOW - 45,
                  "freshness_known": True, "freshness_s": 1}
        first, _ = normalize_snapshot(SourceSnapshot._from_adapter(NOW, values, True, 1),
                                      previous, NOW)
        second, _ = normalize_snapshot(SourceSnapshot._from_adapter(NOW + 30, values, True, 1),
                                       previous, NOW + 30)
        self.assertEqual(first[0].event_id, second[0].event_id)
        self.assertNotIn("stage_occurrence_at", first[0].payload)

    def test_stale_occurrence_identity_survives_polling_and_recovery(self):
        previous = {"stale": False, "freshness_unknown": False}
        first_snapshot = SourceSnapshot._from_adapter(
            NOW, {"freshness_known": True, "freshness_s": 301}, True, 1)
        second_snapshot = SourceSnapshot._from_adapter(
            NOW + 30, {"freshness_known": True, "freshness_s": 331}, True, 1)
        first_events, first_state = normalize_snapshot(first_snapshot, previous, NOW)
        retry_events, retry_state = normalize_snapshot(second_snapshot, previous, NOW + 30)
        self.assertEqual(first_events[0].event_id, retry_events[0].event_id)
        self.assertEqual(first_state["stale_since"], retry_state["stale_since"])
        fresh = SourceSnapshot._from_adapter(
            NOW + 60, {"freshness_known": True, "freshness_s": 1}, True, 1)
        recovered, _ = normalize_snapshot(fresh, first_state, NOW + 60)
        self.assertEqual([event.event_type for event in recovered], ["charger.telemetry_recovered"])

    def test_unknown_to_fresh_emits_recovered_once(self):
        previous = {"stage": "Main Charge", "stale": False, "freshness_unknown": True,
                    "source_failure_started_at": NOW - 90}
        snapshot = SourceSnapshot._from_adapter(
            NOW, {"stage": "Main Charge", "freshness_known": True, "freshness_s": 1}, True, 1)
        events, state = normalize_snapshot(snapshot, previous, NOW)
        self.assertEqual([event.event_type for event in events], ["charger.telemetry_recovered"])
        self.assertFalse(state["freshness_unknown"])

    def test_snapshot_rejects_stale_or_untyped_source(self):
        raw = SourceSnapshot._from_adapter(NOW - 301, {"stage": "Main Charge"}, True, 1)
        with self.assertRaises(ValueError):
            normalize_snapshot({"captured_at": NOW, "source": "ha102_rest_read_only_adapter"}, None, NOW)

    def test_unknown_freshness_does_not_emit_recovered(self):
        events, state = normalize_snapshot(SourceSnapshot._from_adapter(NOW, {"stage": "Main Charge"}, False, None),
                                           {"stale": True}, NOW)
        self.assertEqual([event.event_type for event in events], ["charger.telemetry_unknown"])
        self.assertTrue(state["freshness_unknown"])

    def test_get_only_client_allowlist_credentials_tls_and_payload_mapping(self):
        entity_cfg = Path(__file__).resolve().parents[2] / "config/physical/ha102.yaml"
        entities = load_entity_allowlist(entity_cfg)
        class FakeTransport:
            def __init__(self): self.calls = []
            def get(self, url, headers, timeout, context, max_bytes):
                self.calls.append((url, headers, timeout, context, max_bytes))
                entity = url.rsplit("/", 1)[-1]
                field = next(k for k, v in entities.items() if v == entity)
                state = {"voltage": "14.2", "current": "1.4", "temperature_internal": "24",
                         "temperature_external": "31", "output_state": "1", "autonomous_mode": "off"}.get(field, "0")
                doc = {"entity_id": entity, "state": state, "attributes": {},
                       "last_reported": "2026-11-10T00:00:00+00:00"}
                return json.dumps(doc).encode()
        fake = FakeTransport()
        client = HAReadOnlyClient(HAConfig("https://ha.example", "dummy-token"), entities, transport=fake)
        snap = client.read_snapshot(now=NOW)
        self.assertEqual(snap.provenance, "ha102_rest_read_only_adapter")
        self.assertEqual(snap.values["temperature_internal_c"], 24.0)
        self.assertEqual(snap.values["temperature_external_c"], 31.0)
        self.assertEqual(snap.values["output_state_code"], "1")
        self.assertTrue(snap.freshness_known)
        self.assertEqual(len(fake.calls), len(entities))
        for url, headers, timeout, context, cap in fake.calls:
            self.assertIn("/api/states/sensor.", url) if "binary_sensor" not in url else None
            self.assertEqual(headers["Authorization"], "Bearer dummy-token")
            self.assertEqual(timeout, 5.0)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertEqual(cap, 65536)
        with self.assertRaises(ValueError):
            HAReadOnlyClient(HAConfig("https://ha.example", "x"), entities | {"evil": "switch.rd_6018_output"}, transport=fake)

        class Oversize:
            def get(self, *args): return b"x" * 65537
        client = HAReadOnlyClient(HAConfig("https://ha.example", "dummy-token"), entities, transport=Oversize())
        with self.assertRaisesRegex(SourceError, "size limit") as caught:
            client._read_state(next(iter(entities.values())))
        self.assertNotIn("dummy-token", str(caught.exception))

    def test_missing_ha_timestamps_means_unknown_freshness(self):
        entity_cfg = Path(__file__).resolve().parents[2] / "config/physical/ha102.yaml"
        entities = load_entity_allowlist(entity_cfg)
        class NoTimes:
            def get(self, url, headers, timeout, context, max_bytes):
                entity = url.rsplit("/", 1)[-1]
                return json.dumps({"entity_id": entity, "state": "0", "attributes": {}}).encode()
        snapshot = HAReadOnlyClient(HAConfig("https://ha.example", "dummy"), entities,
                                   transport=NoTimes()).read_snapshot(now=NOW)
        self.assertFalse(snapshot.freshness_known)
        self.assertIsNone(snapshot.freshness_s)

    def test_naive_or_future_ha_timestamps_never_claim_freshness(self):
        entity_cfg = Path(__file__).resolve().parents[2] / "config/physical/ha102.yaml"
        entities = load_entity_allowlist(entity_cfg)
        class FutureTimes:
            def get(self, url, headers, timeout, context, max_bytes):
                entity = url.rsplit("/", 1)[-1]
                field = next(k for k, v in entities.items() if v == entity)
                state = {"voltage": "14.2", "current": "1.4", "temperature_internal": "24",
                         "temperature_external": "31", "output_state": "1"}.get(field, "0")
                return json.dumps({"entity_id": entity, "state": state, "attributes": {},
                                   "last_reported": "2026-11-10T08:41:00"}).encode()
        snapshot = HAReadOnlyClient(HAConfig("https://ha.example", "dummy"), entities,
                                    transport=FutureTimes()).read_snapshot(now=NOW)
        self.assertFalse(snapshot.freshness_known)
        self.assertIsNone(snapshot.freshness_s)

        class FutureReported(FutureTimes):
            def get(self, url, headers, timeout, context, max_bytes):
                entity = url.rsplit("/", 1)[-1]
                field = next(k for k, v in entities.items() if v == entity)
                state = {"voltage": "14.2", "current": "1.4", "temperature_internal": "24",
                         "temperature_external": "31", "output_state": "1"}.get(field, "0")
                return json.dumps({"entity_id": entity, "state": state, "attributes": {},
                                   "last_reported": "2026-11-10T09:42:00Z"}).encode()
        future = HAReadOnlyClient(HAConfig("https://ha.example", "dummy"), entities,
                                  transport=FutureReported()).read_snapshot(now=NOW)
        self.assertFalse(future.freshness_known)
        self.assertIsNone(future.freshness_s)

    def test_dedicated_credentials_fail_closed_without_ha_token_fallback(self):
        with self.assertRaises(SourceError):
            HAConfig.from_env({"HA_TOKEN": "must-not-be-used"})
        with self.assertRaises(SourceError):
            HAConfig.from_env({"RD6018_WAKE_HA_URL": "file:///etc/passwd", "RD6018_WAKE_HA_TOKEN": "dummy"})
        with self.assertRaises(SourceError):
            HAConfig.from_env({"RD6018_WAKE_HA_URL": "https://ha.example", "RD6018_WAKE_HA_TOKEN": "bad" + chr(10) + "header"})

    def test_redirect_handler_refuses_to_forward_bearer_credentials(self):
        from ha_source import _NoRedirect
        from urllib.request import Request
        handler = _NoRedirect()
        request = Request("https://ha.example/api/states/sensor.rd6018")
        self.assertIsNone(handler.redirect_request(
            request, None, 302, "Found", {}, "https://other.example/steal-token"))

    def test_session_parser_only_surfaces_known_safe_metadata(self):
        from ha_source import _read_session_metadata
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "charge_session.json"
            path.write_text(json.dumps({"stage": "Main Charge", "profile": "EFB",
                "v2_trace_session_id": "SECRET_SESSION", "v2_battery_id": "SECRET_BATTERY",
                "main_current_guard_v1": {"journal_schema": 1, "revision": 2,
                    "snapshot": {"fault": "proposal_ack_timeout"}}}))
            os.utime(path, (NOW, NOW))
            values = _read_session_metadata(path, NOW)
            self.assertEqual(values, {"stage": "Main Charge", "profile": "EFB",
                                      "guard_state": "fault", "fault_code": "guard_timeout"})
            os.utime(path, (NOW - 86401, NOW - 86401))
            self.assertEqual(_read_session_metadata(path, NOW), {})
            os.utime(path, (NOW, NOW))
            path.write_text("{")
            self.assertEqual(_read_session_metadata(path), {})
            path.write_text(json.dumps({"stage": [], "profile": {}, "main_current_guard_v1": {
                "journal_schema": True, "revision": 1, "snapshot": {"fault": "proposal_ack_timeout"}}}))
            self.assertEqual(_read_session_metadata(path), {})
            path.unlink()
            path.symlink_to(Path(tmp) / "missing")
            self.assertEqual(_read_session_metadata(path), {})
    def test_local_occurrence_dedupe_survives_restart_and_distinct_occurrence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outbox.sqlite3"
            event = EventEnvelope.for_occurrence("charger.fault", "fault-occurrence-1", NOW, {"fault_code": "OVERTEMP"}, "critical")
            box = Outbox(path, max_events=2, max_age_s=1000)
            self.assertTrue(box.enqueue(event, NOW))
            self.assertFalse(box.enqueue(event, NOW))
            box.close()
            box = Outbox(path, max_events=2, max_age_s=1000)
            self.assertFalse(box.enqueue(EventEnvelope.for_occurrence("charger.fault", "fault-occurrence-1", NOW + 4, {"fault_code": "OVERTEMP"}, "critical"), NOW + 4))
            distinct = EventEnvelope.for_occurrence("charger.fault", "fault-occurrence-2", NOW + 4, {"fault_code": "OVERTEMP"}, "critical")
            self.assertTrue(box.enqueue(distinct, NOW + 4))
            self.assertEqual(len(box.pending()), 2)
            box.close()

    def test_persisted_previous_state_suppresses_same_fault_and_stage_after_restart(self):
        snapshot = SourceSnapshot._from_adapter(NOW, {"stage": "Mix Mode", "stage_occurrence_at": NOW - 60,
            "fault_code": "guard_timeout", "guard_state": "fault", "freshness_known": True,
            "freshness_s": 1}, True, 1)
        old = {"stage": "Main Charge", "fault_code": None, "guard_state": "ok", "stale": False}
        with tempfile.TemporaryDirectory() as tmp:
            box = Outbox(Path(tmp) / "outbox.sqlite3")
            events, current = normalize_snapshot(snapshot, old, NOW)
            for event in events: box.enqueue(event, NOW)
            box.save_state(current)
            box.close()
            box = Outbox(Path(tmp) / "outbox.sqlite3")
            replay, _ = normalize_snapshot(snapshot, box.load_state(), NOW + 30)
            self.assertEqual(replay, [])
            box.close()
    def test_unknown_gateway_result_is_quarantined_and_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Outbox(Path(tmp) / "outbox.sqlite3")
            event = EventEnvelope.for_occurrence("charger.heartbeat", "slot-1", NOW, {"service_state": "running"})
            box.enqueue(event, NOW)
            gateway: EventGatewayClient = FakeGateway(GatewayAcceptance.UNKNOWN)
            self.assertEqual(box.submit_pending_once(gateway), 0)
            self.assertEqual(box.db.execute("select state from events").fetchone()[0], "quarantined_unknown")
            self.assertEqual(box.submit_pending_once(gateway), 0)
            self.assertEqual(len(gateway.events), 1)
            box.close()

    def test_outbox_capacity_and_age_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Outbox(Path(tmp) / "outbox.sqlite3", max_events=1, max_age_s=100)
            first = EventEnvelope.for_occurrence("charger.heartbeat", "slot-a", NOW, {})
            second = EventEnvelope.for_occurrence("charger.heartbeat", "slot-b", NOW + 1, {})
            self.assertTrue(box.enqueue(first, NOW))
            self.assertFalse(box.enqueue(second, NOW + 1))
            self.assertTrue(box.enqueue(second, NOW + 102))
            self.assertEqual(len(box.pending()), 1)
            box.close()

    def test_gateway_acceptance_is_not_delivery_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Outbox(Path(tmp) / "outbox.sqlite3")
            event = EventEnvelope.for_occurrence("charger.heartbeat", "slot-1", NOW, {"service_state": "running"})
            box.enqueue(event, NOW)
            gateway = FakeGateway(GatewayAcceptance.ACCEPTED)
            self.assertEqual(box.submit_pending_once(gateway), 1)
            self.assertEqual(box.db.execute("select state from events").fetchone()[0], "gateway_accepted")
            self.assertEqual(box.pending(), [])
            box.close()

    def test_no_route_config_and_client_is_only_a_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"schema": 1}))
            path.chmod(0o600)
            self.assertNotIn("route", load_config(path))
        self.assertTrue(getattr(EventGatewayClient, "_is_protocol", False))
        with self.assertRaisesRegex(RuntimeError, "not published or wired"):
            UnwiredEventGatewayClient().submit(EventEnvelope.for_occurrence(
                "charger.heartbeat", "slot", NOW, {}))

    def test_config_permissions_ranges_and_unknown_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"schema": 1, "entity_config": "config/physical/ha102.yaml"}))
            path.chmod(0o600)
            self.assertEqual(load_config(path)["poll_interval_s"], 30)
            path.write_text(json.dumps({"schema": 1, "route": "chat-route"}))
            with self.assertRaises(ValueError):
                load_config(path)
            path.write_text(json.dumps({"schema": 1}))
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                load_config(path)

if __name__ == "__main__":
    unittest.main()
