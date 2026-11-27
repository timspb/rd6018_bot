"""Fake-only behavior contracts for restored-session finalization."""

import unittest
from unittest.mock import patch

import charge_controller as charge_controller_module
from charge_controller import ManagedChargeController
from runtime.charge.restore_finalization import finalize_restored_session
from runtime.charge.session import RestoredSessionDocument
from runtime.charge.session_atomic import WriteStatus


class RestoreFinalizationUseCaseTests(unittest.TestCase):
    def make_host(self):
        host = type("Host", (), {})()
        host._session_restore_enriched = True
        host._session_restore_snapshot = None
        host._stage_tracking_enabled = False
        host.events = []
        host._save_session = lambda *_args, **_kwargs: (WriteStatus.COMMITTED, b"preimage")
        return host

    def test_normal_restore_captures_snapshot_before_enabling_tracking(self):
        host = self.make_host()
        document = {"stage": "MAIN"}
        finalize_restored_session(
            host, document, normalize_done_document=False,
            normalize_terminal=lambda *_args, **_kwargs: self.fail("unexpected normalize"),
            session_file="unused", restored_terminal=False,
            voltage=12.0, current=1.0, ah=2.0,
            canonical_preimage=b"preimage",
        )
        self.assertIsInstance(host._session_restore_snapshot, RestoredSessionDocument)
        self.assertEqual(host._session_restore_snapshot.document, document)
        self.assertTrue(host._stage_tracking_enabled)
        self.assertTrue(host._session_restore_enriched)

    def test_done_normalizer_runs_before_snapshot(self):
        host = self.make_host()
        document = {"stage": "Done"}

        def normalize(_host, _document, *, session_file):
            host.events.append(("normalize", session_file, host._stage_tracking_enabled))
            return True

        original_capture = RestoredSessionDocument.capture

        def capture(data):
            host.events.append(("snapshot", host._stage_tracking_enabled))
            return original_capture(data)

        RestoredSessionDocument.capture = staticmethod(capture)
        try:
            finalize_restored_session(
                host, document, normalize_done_document=True,
                normalize_terminal=normalize, session_file="session.json",
                restored_terminal=False, voltage=12.0, current=1.0, ah=2.0,
                canonical_preimage=b"preimage",
            )
        finally:
            RestoredSessionDocument.capture = classmethod(
                lambda cls, data: original_capture(data)
            )
        self.assertEqual(host.events, [
            ("normalize", "session.json", False), ("snapshot", False),
        ])
        self.assertTrue(host._session_restore_enriched)
        self.assertTrue(host._stage_tracking_enabled)

    def test_expired_mix_snapshot_precedes_terminal_save_with_tracking_off(self):
        host = self.make_host()
        def save(*args, **kwargs):
            host.events.append(("save", args, kwargs, host._stage_tracking_enabled,
                                isinstance(host._session_restore_snapshot, RestoredSessionDocument)))
            return WriteStatus.COMMITTED, b"preimage"
        host._save_session = save
        finalize_restored_session(
            host, {"stage": "Mix"}, normalize_done_document=False,
            normalize_terminal=lambda *_args, **_kwargs: False,
            session_file="unused", restored_terminal=True,
            voltage=14.4, current=0.2, ah=3.0,
            canonical_preimage=b"preimage",
        )
        self.assertEqual(host.events, [("save", (14.4, 0.2, 3.0), {"restore_expected_bytes": b"preimage"}, False, True)])
        self.assertTrue(host._session_restore_enriched)
        self.assertTrue(host._stage_tracking_enabled)

    def test_normalizer_exception_prevents_snapshot_and_tracking(self):
        host = self.make_host()

        def fail(*_args, **_kwargs):
            host.events.append("normalize")
            raise RuntimeError("normalizer failed")

        with self.assertRaisesRegex(RuntimeError, "normalizer failed"):
            finalize_restored_session(
                host, {"stage": "Done"}, normalize_done_document=True,
                normalize_terminal=fail, session_file="unused",
                restored_terminal=False, voltage=12.0, current=1.0, ah=2.0,
                canonical_preimage=b"preimage",
            )
        self.assertEqual(host.events, ["normalize"])
        self.assertIsNone(host._session_restore_snapshot)
        self.assertFalse(host._stage_tracking_enabled)

    def test_save_exception_keeps_snapshot_and_tracking_off(self):
        host = self.make_host()

        def fail_save(*_args, **_kwargs):
            host.events.append(("save", host._stage_tracking_enabled))
            raise RuntimeError("save failed")

        host._save_session = fail_save
        with self.assertRaisesRegex(RuntimeError, "save failed"):
            finalize_restored_session(
                host, {"stage": "Mix"}, normalize_done_document=False,
                normalize_terminal=lambda *_args, **_kwargs: False,
                session_file="unused", restored_terminal=True,
                voltage=14.4, current=0.2, ah=3.0,
                canonical_preimage=b"preimage",
            )
        self.assertIsInstance(host._session_restore_snapshot, RestoredSessionDocument)
        self.assertEqual(host.events, [("save", False)])
        self.assertFalse(host._stage_tracking_enabled)

    def test_successful_terminal_save_marks_enrichment_true(self):
        host = self.make_host()
        host._session_restore_enriched = False
        def save(*_args, **_kwargs):
            host.events.append("save")
            return WriteStatus.COMMITTED, b"preimage"
        host._save_session = save
        finalize_restored_session(
            host, {"stage": "Mix"}, normalize_done_document=False,
            normalize_terminal=lambda *_args, **_kwargs: False,
            session_file="unused", restored_terminal=True,
            voltage=14.4, current=0.2, ah=3.0,
            canonical_preimage=b"preimage",
        )
        self.assertEqual(host.events, ["save"])
        self.assertTrue(host._session_restore_enriched)
        self.assertTrue(host._stage_tracking_enabled)

    def test_finalizer_has_no_physical_port_calls(self):
        host = self.make_host()
        host.physical_calls = []
        for name in ("_device_set_voltage", "_device_set_current", "_set_output"):
            setattr(host, name, lambda *_args, _name=name: host.physical_calls.append(_name))
        finalize_restored_session(
            host, {"stage": "MAIN"}, normalize_done_document=False,
            normalize_terminal=lambda *_args, **_kwargs: False,
            session_file="unused", restored_terminal=False,
            voltage=12.0, current=1.0, ah=2.0,
            canonical_preimage=b"preimage",
        )
        self.assertEqual(host.physical_calls, [])

    def test_only_committed_result_enables_tracking(self):
        for status in (WriteStatus.NOT_COMMITTED, WriteStatus.OUTCOME_UNCERTAIN, None):
            host = self.make_host()
            calls = []
            host._save_session = lambda *_args, **_kwargs: (calls.append("commit") or status, b"observed")
            with self.assertRaisesRegex(RuntimeError, str(getattr(status, "value", status))):
                finalize_restored_session(
                    host, {"stage": "MAIN"}, normalize_done_document=False,
                    normalize_terminal=lambda *_args, **_kwargs: False,
                    session_file="unused", restored_terminal=False,
                    voltage=12.0, current=1.0, ah=2.0, canonical_preimage=b"preimage",
                )
            self.assertEqual(calls, ["commit"])
            self.assertFalse(host._stage_tracking_enabled)

    def test_noop_restore_commit_passes_exact_preimage(self):
        host = self.make_host()
        args = []
        host._save_session = lambda *a, **kw: (args.append((a, kw)) or (WriteStatus.COMMITTED, b"same"))
        finalize_restored_session(
            host, {"stage": "MAIN"}, normalize_done_document=False,
            normalize_terminal=lambda *_args, **_kwargs: False,
            session_file="unused", restored_terminal=False,
            voltage=12.0, current=1.0, ah=2.0, canonical_preimage=b"same",
        )
        self.assertEqual(args, [((12.0, 1.0, 2.0), {"restore_expected_bytes": b"same"})])

    def test_charge_controller_save_session_propagates_write_status_result(self):
        controller = ManagedChargeController.__new__(ManagedChargeController)
        for status in (WriteStatus.COMMITTED, WriteStatus.OUTCOME_UNCERTAIN):
            with self.subTest(status=status):
                observed_bytes = b"observed preimage"
                sentinel = (status, observed_bytes)
                with patch.object(
                    charge_controller_module, "save_session", return_value=sentinel,
                ) as save:
                    result = controller._save_session(
                        12.3, 0.4, 1.2, restore_expected_bytes=b"expected preimage",
                    )

                self.assertIs(result, sentinel)
                save.assert_called_once_with(
                    controller, 12.3, 0.4, 1.2,
                    session_file=charge_controller_module.SESSION_FILE,
                    terminal_request=None,
                    restore_expected_bytes=b"expected preimage",
                )


if __name__ == "__main__":
    unittest.main()
