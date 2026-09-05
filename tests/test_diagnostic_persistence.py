import os
import tempfile
import unittest

from diagnostic_persistence import (
    DiagnosticActionJournal,
    DiagnosticActionKind,
    DiagnosticActionStatus,
    recover_diagnostic_persistence,
)


class DiagnosticActionJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tempdir.name, "diagnostic_actions.json")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_restart_matrix_never_resumes_authoritative_actions(self) -> None:
        journal = DiagnosticActionJournal(self.path)
        probe = journal.begin(
            DiagnosticActionKind.PROBE,
            battery_id="battery-a",
            status=DiagnosticActionStatus.RUNNING,
            now=100.0,
        )
        confirmation = journal.begin(
            DiagnosticActionKind.OPERATOR_CONFIRMATION,
            battery_id="battery-a",
            status=DiagnosticActionStatus.PENDING,
            now=100.0,
        )
        expert = journal.begin(
            DiagnosticActionKind.EXPERT_HV_AUTHORIZATION,
            battery_id="battery-a",
            status=DiagnosticActionStatus.ACTIVE,
            now=100.0,
        )
        rest = journal.begin(
            DiagnosticActionKind.REST_OBSERVATION,
            battery_id="battery-a",
            status=DiagnosticActionStatus.ACTIVE,
            expires_at=1000.0,
            now=100.0,
        )

        restored = DiagnosticActionJournal(self.path)
        changed = restored.recover_after_restart(now=200.0)
        changed_by_id = {record.action_id: record for record in changed}
        all_by_id = {record.action_id: record for record in restored.records}

        self.assertEqual(
            changed_by_id[probe.action_id].status,
            DiagnosticActionStatus.ABORTED_RESTART,
        )
        self.assertEqual(
            changed_by_id[confirmation.action_id].status,
            DiagnosticActionStatus.EXPIRED_RESTART,
        )
        self.assertEqual(
            changed_by_id[expert.action_id].status,
            DiagnosticActionStatus.REVOKED_RESTART,
        )
        self.assertNotIn(rest.action_id, changed_by_id)
        self.assertEqual(
            all_by_id[rest.action_id].status,
            DiagnosticActionStatus.ACTIVE,
        )

    def test_expired_rest_window_does_not_survive_restart(self) -> None:
        journal = DiagnosticActionJournal(self.path)
        rest = journal.begin(
            DiagnosticActionKind.REST_OBSERVATION,
            battery_id="battery-a",
            status=DiagnosticActionStatus.ACTIVE,
            expires_at=150.0,
            now=100.0,
        )

        restored = DiagnosticActionJournal(self.path)
        changed = restored.recover_after_restart(now=200.0)

        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].action_id, rest.action_id)
        self.assertEqual(changed[0].status, DiagnosticActionStatus.EXPIRED)
        self.assertEqual(restored.active(), [])

    def test_completed_evidence_action_is_not_rewritten(self) -> None:
        journal = DiagnosticActionJournal(self.path)
        action = journal.begin(
            DiagnosticActionKind.PROBE,
            battery_id="battery-a",
            now=100.0,
        )
        journal.update(
            action.action_id,
            status=DiagnosticActionStatus.COMPLETED,
            note="probe_recorded",
            now=120.0,
        )

        restored = DiagnosticActionJournal(self.path)
        changed = restored.recover_after_restart(now=200.0)

        self.assertEqual(changed, [])
        self.assertEqual(
            restored.records[0].status,
            DiagnosticActionStatus.COMPLETED,
        )


class _FakeHass:
    def __init__(self, *, off_result=True, off_raises=False) -> None:
        self.turn_off_calls = 0
        self.off_result = off_result
        self.off_raises = off_raises

    async def turn_off(self) -> bool:
        self.turn_off_calls += 1
        if self.off_raises:
            raise RuntimeError("synthetic OFF failure")
        return self.off_result


class _FakeApp:
    def __init__(
        self,
        journal: DiagnosticActionJournal,
        *,
        off_result=True,
        off_raises=False,
    ) -> None:
        self.hass = _FakeHass(off_result=off_result, off_raises=off_raises)
        self.diagnostic_action_journal = journal
        self.notifications = []

    def _charge_notify(self, message: str, critical: bool = True) -> None:
        self.notifications.append((message, critical))


class DiagnosticRestartRecoveryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _journal_with_interrupted_probe(path):
        journal = DiagnosticActionJournal(path)
        journal.begin(
            DiagnosticActionKind.PROBE,
            battery_id="battery-a",
            status=DiagnosticActionStatus.RUNNING,
            now=100.0,
        )
        return DiagnosticActionJournal(path)

    async def test_interrupted_probe_forces_output_off_and_notifies(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "diagnostic_actions.json")
            app = _FakeApp(self._journal_with_interrupted_probe(path))

            changed = await recover_diagnostic_persistence(app)

            self.assertTrue(
                any(
                    record.status is DiagnosticActionStatus.ABORTED_RESTART
                    for record in changed
                )
            )
            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(len(app.notifications), 1)
            self.assertTrue(app.notifications[0][1])
            self.assertIn("подтверждён OFF", app.notifications[0][0])

    async def test_interrupted_probe_never_claims_off_when_shutdown_is_unconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "diagnostic_actions.json")
            app = _FakeApp(
                self._journal_with_interrupted_probe(path),
                off_result=False,
            )

            await recover_diagnostic_persistence(app)

            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(len(app.notifications), 1)
            self.assertIn("НЕ ПОДТВЕРЖДЁН", app.notifications[0][0])
            self.assertNotIn("подтверждён OFF", app.notifications[0][0])

    async def test_interrupted_probe_off_exception_is_reported_as_unconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "diagnostic_actions.json")
            app = _FakeApp(
                self._journal_with_interrupted_probe(path),
                off_raises=True,
            )

            await recover_diagnostic_persistence(app)

            self.assertEqual(app.hass.turn_off_calls, 1)
            self.assertEqual(len(app.notifications), 1)
            self.assertIn("НЕ ПОДТВЕРЖДЁН", app.notifications[0][0])


if __name__ == "__main__":
    unittest.main()
