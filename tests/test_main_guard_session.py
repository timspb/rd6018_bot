"""Canonical MAIN Guard persistence: offline temp files, no real node/actuator."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.main_guard_session import (
    GUARD_KEY, GuardJournalError, read_guard, attach_guard,
    atomic_write_guard_session,
)


def identity():
    return {
        "v2_trace_session_id": "sid", "v2_battery_id": "bat",
        "profile": "EFB", "stage": "Main Charge", "ah_limit": 72,
        "target_current": 7.2,
    }


def guard():
    return MainCurrentGuard.start(
        session_id="sid", battery_id="bat", segment_id="main-1",
        capacity_ah=72, recipe_initial_current_a=12.0,
    )


def proposed():
    g, _ = guard().observe(now_s=0, output_on=True, measured_current_a=4, fresh=True)
    return g.observe(now_s=1800, output_on=True, measured_current_a=4, fresh=True)


class MainGuardSessionContractTests(unittest.TestCase):
    def test_initial_snapshot_in_canonical_document(self):
        record = attach_guard(identity(), guard(), now_s=1, expected_revision=0)
        restored, revision = read_guard(record, session_id="sid", battery_id="bat", now_s=2)
        self.assertEqual(revision, 1)
        self.assertEqual(restored.hardware_limit_a, 7.2)
        self.assertFalse(restored.last_output_on)
        self.assertEqual(record["profile"], "EFB")

    def test_immutable_session_and_battery_identity(self):
        for key, replacement in (
            ("v2_trace_session_id", "other"), ("v2_battery_id", "other"),
            ("ah_limit", 100), ("profile", "AGM"), ("stage", "Mix Mode")
        ):
            with self.subTest(key=key):
                doc = identity()
                doc[key] = replacement
                with self.assertRaises(GuardJournalError):
                    attach_guard(doc, guard(), now_s=1, expected_revision=0)

    def test_tampering_hash_and_corrupt_schema_fail(self):
        doc = attach_guard(identity(), guard(), now_s=1, expected_revision=0)
        other = copy.deepcopy(doc)
        other[GUARD_KEY]["snapshot"]["hardware_limit_a"] = 12
        with self.assertRaisesRegex(GuardJournalError, "integrity"):
            read_guard(other, session_id="sid", battery_id="bat", now_s=2)
        other = copy.deepcopy(doc)
        other[GUARD_KEY]["journal_schema"] = 99
        with self.assertRaisesRegex(GuardJournalError, "schema"):
            read_guard(other, session_id="sid", battery_id="bat", now_s=2)

    def test_absent_checkpoint_is_not_factory_default(self):
        with self.assertRaisesRegex(GuardJournalError, "absent"):
            read_guard(identity(), session_id="sid", battery_id="bat", now_s=1)
        with self.assertRaisesRegex(GuardJournalError, "missing"):
            attach_guard(identity(), guard(), now_s=1, expected_revision=1)

    def test_stale_revision_refused(self):
        doc = attach_guard(identity(), guard(), now_s=1, expected_revision=0)
        with self.assertRaisesRegex(GuardJournalError, "stale"):
            attach_guard(doc, guard(), now_s=2, expected_revision=0)

    def test_new_segment_and_cap_increase_not_implicitly_authorized(self):
        doc = attach_guard(identity(), guard(), now_s=1, expected_revision=0)
        altered = guard()
        from dataclasses import replace
        with self.assertRaisesRegex(GuardJournalError, "epoch"):
            attach_guard(doc, replace(altered, segment_id="main-2"),
                         now_s=2, expected_revision=1)
        g, pending = proposed()
        committed = g.commit(
            proposal_id=pending.proposal_id, now_s=1801,
            measured_current_a=4, measured_current_fresh=True,
            current_limit_readback_a=5, current_readback_fresh=True,
            ocp_limit_a=5.1, ocp_readback_fresh=True,
        )
        doc = attach_guard(doc, committed, now_s=1802, expected_revision=1)
        with self.assertRaisesRegex(GuardJournalError, "enlarged"):
            attach_guard(doc, altered, now_s=1803, expected_revision=2)

    def test_pending_cannot_be_erased_without_proven_reduction(self):
        from dataclasses import replace
        g, pending = proposed()
        doc = attach_guard(identity(), g, now_s=1801, expected_revision=0)
        erased = replace(g, pending=None)
        with self.assertRaisesRegex(GuardJournalError, "cannot_disappear"):
            attach_guard(doc, erased, now_s=1802, expected_revision=1)
        proven = g.commit(
            proposal_id=pending.proposal_id, now_s=1802,
            measured_current_a=4, measured_current_fresh=True,
            current_limit_readback_a=5, current_readback_fresh=True,
            ocp_limit_a=5.1, ocp_readback_fresh=True,
        )
        next_doc = attach_guard(doc, proven, now_s=1803, expected_revision=1)
        self.assertEqual(next_doc[GUARD_KEY]["revision"], 2)
        self.assertEqual(read_guard(next_doc, session_id="sid",
                                    battery_id="bat", now_s=1804)[0].hardware_limit_a, 5)

    def test_crash_restart_preserves_monotone_cap_and_pending(self):
        g, pending = proposed()
        doc = attach_guard(identity(), g, now_s=1801, expected_revision=0)
        restored, rev = read_guard(doc, session_id="sid", battery_id="bat", now_s=1802)
        self.assertEqual(restored.pending, pending)
        self.assertEqual(restored.hardware_limit_a, 7.2)
        self.assertFalse(restored.last_output_on)
        self.assertEqual(rev, 1)

    def test_atomic_replacement_same_file_and_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "charge_session.json"
            p.write_text(json.dumps(identity()), encoding="utf-8")
            self.assertEqual(atomic_write_guard_session(
                p, guard(), now_s=1, expected_revision=0), 1)
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(raw["target_current"], 7.2)
            self.assertIn(GUARD_KEY, raw)
            self.assertFalse(list(p.parent.glob(".main-guard-*.tmp")))
            self.assertEqual(atomic_write_guard_session(
                p, guard(), now_s=2, expected_revision=1), 2)

    def test_disk_failure_does_not_reinitialize_missing_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "charge_session.json"
            with self.assertRaisesRegex(GuardJournalError, "unavailable"):
                atomic_write_guard_session(p, guard(), now_s=1, expected_revision=0)


if __name__ == "__main__":
    unittest.main()
