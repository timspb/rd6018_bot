"""Fake-only persistence contract for AD039 interruption markers."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.charge import persistence, restore_admission


def _doc(**changes):
    value = {
        "profile": "Ca/Ca", "stage": "Main Charge", "ah_limit": 60,
        "saved_at": 1700000100.0, "total_start_time": 1700000000.0,
        "stage_start_time": 1700000001.0, "target_voltage": 14.4,
        "target_current": 1.0, "stage_history": [{"x": [1, None]}],
        "safe_wait_next_stage": "Main Charge", "v2_trace_session_id": "s-1",
        "v2_trace_started_at": 1700000000.0, "v2_battery_id": "b-1",
        "extension_evidence": {"keep": True},
    }
    value.update(changes)
    return value


def _identity(doc):
    ident = restore_admission.session_identity(doc)
    return ident


class InterruptionMarkerAD039Tests(unittest.TestCase):
    def test_mark_preserves_every_decoded_value_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "charge_session.json"
            original = _doc()
            path.write_text(json.dumps(original), encoding="utf-8")
            raw = path.read_bytes()
            args = dict(expected_document_sha256=hashlib.sha256(raw).hexdigest(),
                        expected_identity=_identity(original),
                        recorded_at_utc="2026-11-13T01:02:03+00:00")
            self.assertTrue(persistence.mark_session_interrupted(str(path), **args))
            first = json.loads(path.read_text(encoding="utf-8"))
            marker = first.pop("interruption_v1")
            self.assertEqual(first, original)
            self.assertEqual(restore_admission.validate_interruption_marker(json.loads(path.read_text())), "interrupted")
            marked_raw = path.read_bytes()
            self.assertTrue(persistence.mark_session_interrupted(
                str(path), expected_document_sha256=hashlib.sha256(marked_raw).hexdigest(),
                expected_identity=_identity(original), recorded_at_utc="2026-11-14T00:00:00+00:00"))
            self.assertEqual(json.loads(path.read_text())["interruption_v1"], marker)

    def test_marker_classification_is_exact_and_malformed_blocks_restore(self):
        doc = _doc()
        self.assertEqual(restore_admission.validate_interruption_marker(doc), "absent")
        marker = {"schema_version": 1, "owner": "runtime.charge.persistence",
                  "state": "interrupted", "reason": "process_restart", "rearmable": False,
                  "recorded_at_utc": "2026-11-13T01:02:03+00:00",
                  "session_identity": _identity(doc)}
        self.assertEqual(restore_admission.validate_interruption_marker(doc | {"interruption_v1": marker}), "interrupted")
        for bad in (marker | {"schema_version": 2}, marker | {"reason": "other"},
                    marker | {"session_identity": {"session_id": "different"}},
                    marker | {"recorded_at_utc": "bad"}, "bad"):
            self.assertEqual(restore_admission.validate_interruption_marker(
                doc | {"interruption_v1": bad}), "blocked")

    def test_restore_veto_precedes_any_host_mutation(self):
        class Host:
            PROFILE_CA = "Ca/Ca"
            STAGE_IDLE = "Idle"
            def __init__(self): self.values = {"sentinel": 1}
            def __setattr__(self, name, value):
                if name == "values": object.__setattr__(self, name, value)
                else: raise AssertionError("restore mutated host")
        doc = _doc()
        marker = {"schema_version": 1, "owner": "runtime.charge.persistence",
                  "state": "interrupted", "reason": "process_restart", "rearmable": False,
                  "recorded_at_utc": "2026-11-13T01:02:03+00:00",
                  "session_identity": _identity(doc)}
        for value in (marker, marker | {"schema_version": 77}):
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "session.json"
                path.write_text(json.dumps(doc | {"interruption_v1": value}), encoding="utf-8")
                host = Host()
                before = dict(host.values)
                result = persistence.restore_session(host, 0, 0, 0, session_file=str(path))
                self.assertFalse(result[0])
                self.assertEqual(host.values, before)

    def test_identity_mismatch_writer_failure_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "session.json"
            original = _doc()
            path.write_text(json.dumps(original), encoding="utf-8")
            raw = path.read_bytes()
            common = dict(expected_document_sha256=hashlib.sha256(raw).hexdigest(),
                          expected_identity=_identity(original),
                          recorded_at_utc="2026-11-13T01:02:03+00:00")
            mismatch = dict(common, expected_identity={"session_id": "wrong", "started_at": 1, "battery_id": None})
            self.assertFalse(persistence.mark_session_interrupted(str(path), **mismatch))
            invalid_time = dict(common, recorded_at_utc="not-a-time")
            self.assertFalse(persistence.mark_session_interrupted(str(path), **invalid_time))
            with patch.object(persistence, "atomic_session_write", side_effect=OSError("injected")):
                self.assertFalse(persistence.mark_session_interrupted(str(path), **common))
            self.assertEqual(path.read_bytes(), raw)
            link = Path(temp) / "link.json"
            try:
                link.symlink_to(path)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            self.assertFalse(persistence.mark_session_interrupted(str(link), **common))

    def test_historical_unmarked_document_and_legacy_projection(self):
        legacy = _doc()
        for key in ("v2_trace_session_id", "v2_trace_started_at", "v2_battery_id"):
            legacy.pop(key)
        first = restore_admission.session_identity(legacy)
        second = restore_admission.session_identity(legacy)
        self.assertEqual(first, second)
        self.assertIsNone(restore_admission.session_identity({"stage": "Main Charge"}))
        self.assertEqual(restore_admission.validate_interruption_marker(_doc()), "absent")


if __name__ == "__main__":
    unittest.main()
