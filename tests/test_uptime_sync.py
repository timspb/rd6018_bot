import unittest

from runtime.startup_recovery import (
    apply_restore_time_corrections,
    sync_total_start_from_uptime,
)


class _FakeController:
    def __init__(self, *, is_active=True, total_start_time=0.0, stage_start_time=0.0, link_lost_at=0.0):
        self.is_active = is_active
        self.total_start_time = total_start_time
        self.stage_start_time = stage_start_time
        self._link_lost_at = link_lost_at


class UptimeSyncTests(unittest.TestCase):
    def setUp(self):
        self.fixed_now = 1_000_000.0

    def test_sync_updates_when_drift_within_limit(self):
        sync = sync_total_start_from_uptime
        controller = _FakeController(is_active=True, total_start_time=self.fixed_now - 1200)

        changed = sync(
            controller,
            {"uptime": 1220},
            max_drift_sec=300,
            allow_init=False,
            now_s=self.fixed_now,
        )

        self.assertTrue(changed)
        self.assertAlmostEqual(controller.total_start_time, self.fixed_now - 1220)

    def test_sync_rejects_when_drift_too_large(self):
        sync = sync_total_start_from_uptime
        controller = _FakeController(is_active=True, total_start_time=self.fixed_now - 1200)

        changed = sync(
            controller,
            {"uptime": 1700},
            max_drift_sec=300,
            allow_init=False,
            now_s=self.fixed_now,
        )

        self.assertFalse(changed)
        self.assertAlmostEqual(controller.total_start_time, self.fixed_now - 1200)

    def test_sync_does_not_init_when_allow_init_false(self):
        sync = sync_total_start_from_uptime
        controller = _FakeController(is_active=True, total_start_time=0.0)

        changed = sync(
            controller,
            {"uptime": 300},
            max_drift_sec=300,
            allow_init=False,
            now_s=self.fixed_now,
        )

        self.assertFalse(changed)
        self.assertEqual(controller.total_start_time, 0.0)

    def test_apply_restore_shifts_timers_and_syncs_if_close(self):
        apply_restore = apply_restore_time_corrections
        controller = _FakeController(
            is_active=True,
            total_start_time=self.fixed_now - 3600,
            stage_start_time=self.fixed_now - 900,
            link_lost_at=self.fixed_now - 60,
        )

        apply_restore(controller, {"uptime": 3650}, now_s=self.fixed_now)

        self.assertEqual(controller._link_lost_at, 0)
        self.assertAlmostEqual(controller.stage_start_time, self.fixed_now - 840)
        self.assertAlmostEqual(controller.total_start_time, self.fixed_now - 3650)

    def test_apply_restore_does_not_overwrite_with_far_uptime(self):
        apply_restore = apply_restore_time_corrections
        controller = _FakeController(
            is_active=True,
            total_start_time=self.fixed_now - 3600,
            stage_start_time=self.fixed_now - 900,
            link_lost_at=self.fixed_now - 60,
        )

        apply_restore(controller, {"uptime": 10}, now_s=self.fixed_now)

        self.assertEqual(controller._link_lost_at, 0)
        self.assertAlmostEqual(controller.total_start_time, self.fixed_now - 3540)
        self.assertAlmostEqual(controller.stage_start_time, self.fixed_now - 840)


if __name__ == "__main__":
    unittest.main()
