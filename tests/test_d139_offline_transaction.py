import tempfile
import unittest
from pathlib import Path

from tools.d139_offline_transaction import OfflineTransition, D139Error, SENTINEL


class FakeService:
    d139_offline_fixture = True

    def __init__(self):
        self.active = True
        self.starts = 0
        self.stops = 0
    def stop(self):
        self.active = False
        self.stops += 1
    def start(self):
        self.active = True
        self.starts += 1


class D139Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="d139-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / SENTINEL).write_text("offline only")
        for name in ("app", "venv", "state", "d139-candidate/app", "d139-candidate/venv"):
            (self.root / name).mkdir(parents=True)
        (self.root / "app/version").write_text("old source")
        (self.root / "venv/version").write_text("old environment")
        (self.root / "d139-candidate/app/version").write_text("candidate source")
        (self.root / "d139-candidate/venv/version").write_text("candidate environment")
        (self.root / "state/session.json").write_text("RETIRED")
        (self.root / "D090_TRANSACTION.json").write_text("STARTED-without-inventory")
        (self.root / ".deploy_sha").write_text("legacy marker")
        self.service = FakeService()

    def assert_legacy_untouched(self):
        self.assertEqual((self.root / "state/session.json").read_text(), "RETIRED")
        self.assertEqual((self.root / "D090_TRANSACTION.json").read_text(), "STARTED-without-inventory")
        self.assertEqual((self.root / ".deploy_sha").read_text(), "legacy marker")

    def test_success_fixture_then_recover_exact_old_bytes(self):
        t = OfflineTransition(self.root, self.service)
        result = t.activate_fixture()
        self.assertEqual(result["phase"], "CANDIDATE_RUNNING")
        self.assertEqual((self.root / "app/version").read_text(), "candidate source")
        self.assertEqual((self.root / "venv/version").read_text(), "candidate environment")
        self.assert_legacy_untouched()
        self.assertEqual(t.recover_fixture()["phase"], "RESTORED")
        self.assertEqual((self.root / "app/version").read_text(), "old source")
        self.assertEqual((self.root / "venv/version").read_text(), "old environment")
        self.assertTrue(self.service.active)
        self.assert_legacy_untouched()

    def test_crash_boundaries_preserve_state_and_restore(self):
        for point in ("BACKUP_DURABLE", "STOPPED",
                      "AFTER_OLD_APP_RENAME_BEFORE_JOURNAL", "OLD_APP_RENAMED",
                      "AFTER_NEW_APP_RENAME_BEFORE_JOURNAL", "NEW_APP_RENAMED",
                      "AFTER_OLD_VENV_RENAME_BEFORE_JOURNAL", "OLD_VENV_RENAMED",
                      "AFTER_NEW_VENV_RENAME_BEFORE_JOURNAL", "NEW_VENV_RENAMED",
                      "CANDIDATE_RUNNING"):
            with self.subTest(point=point):
                self.setUp()
                def fail(name):
                    if name == point:
                        raise RuntimeError("crash at " + point)
                t = OfflineTransition(self.root, self.service, failpoint=fail)
                with self.assertRaisesRegex(RuntimeError, "crash"):
                    t.activate_fixture()
                self.assert_legacy_untouched()
                clean = OfflineTransition(self.root, self.service)
                self.assertEqual(clean.recover_fixture()["phase"], "RESTORED")
                self.assertEqual((self.root / "app/version").read_text(), "old source")
                self.assertEqual((self.root / "venv/version").read_text(), "old environment")
                self.assert_legacy_untouched()

    def test_prepared_without_backup_never_stops_service_for_recovery(self):
        def fail(name):
            if name == "PREPARED":
                raise RuntimeError("crash before backup")
        t = OfflineTransition(self.root, self.service, failpoint=fail)
        with self.assertRaises(RuntimeError):
            t.activate_fixture()
        stop_before = self.service.stops
        with self.assertRaises(D139Error):
            OfflineTransition(self.root, self.service).recover_fixture()
        self.assertEqual(stop_before, self.service.stops)
        self.assert_legacy_untouched()

    def test_corrupt_backup_refuses_before_stop(self):
        t = OfflineTransition(self.root, self.service)
        t.activate_fixture()
        (self.root / "d139-backup/app/version").write_text("corrupted")
        stops_before = self.service.stops
        with self.assertRaisesRegex(D139Error, "rollback preimage"):
            t.recover_fixture()
        self.assertEqual(self.service.stops, stops_before)
        self.assert_legacy_untouched()

    def test_recovery_preserves_new_session_data(self):
        t = OfflineTransition(self.root, self.service)
        t.activate_fixture()
        # A resumed service can persist new state after candidate START.
        (self.root / "state/session.json").write_text("RETIRED with new diagnostic")
        t.recover_fixture()
        self.assertEqual((self.root / "state/session.json").read_text(),
                         "RETIRED with new diagnostic")
        self.assertEqual((self.root / "app/version").read_text(), "old source")
        self.assertEqual((self.root / "venv/version").read_text(), "old environment")

    def test_non_fixture_service_denied(self):
        service = FakeService()
        service.d139_offline_fixture = False
        with self.assertRaisesRegex(D139Error, "isolated"):
            OfflineTransition(self.root, service)

    def test_missing_fixture_sentinel(self):
        (self.root / SENTINEL).unlink()
        with self.assertRaisesRegex(D139Error, "isolated"):
            OfflineTransition(self.root, self.service)


if __name__ == "__main__":
    unittest.main()
