import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.acceptance_guard import transient
from tools.acceptance_guard.transient import TransientAcceptance


class FakeClient:
    def __init__(self, events, *, safe=True, telemetry='on', dwell_ready=True,
                 guard=None, protection=0, protection_age=1, protection_status='ok', lose_at=None):
        self.events, self.safe, self.telemetry = events, safe, telemetry
        self.dwell_ready = dwell_ready
        self.guard, self.protection, self.protection_age = guard, protection, protection_age
        self.protection_status, self.lose_at = protection_status, lose_at
        self.reads = 0
        self.enabled = False
    async def get_all_live(self):
        self.reads += 1
        state = 'on' if self.enabled else 'off'
        if self.guard is None and self.enabled:
            state = self.telemetry
        if self.lose_at is not None and self.reads >= self.lose_at:
            state = 'unavailable'
        code = 0.0 if state == 'off' else (1.0 if state == 'on' else None)
        if self.guard is not None:
            self.guard.observe(state == 'on', self.guard.clock(), valid=state in ('on', 'off'))
        self.events.append('raw protection')
        return {'switch': state, 'output_state_code_v2': code, 'protection_code': self.protection,
                'temp_int': 30.0, 'temp_ext': 24.0,
                '_meta': {**{k: {'status': 'ok', 'age_s': 1} for k in ('switch', 'output_state_code_v2', 'temp_int', 'temp_ext')},
                          'protection_code': {'status': self.protection_status, 'age_s': self.protection_age}}}
    async def safe_enable_output(self, **kwargs):
        self.events.append('enable')
        if not self.dwell_ready:
            raise RuntimeError('canonical 12 second report dwell not satisfied')
        self.enabled = self.safe
        return SimpleNamespace(enabled=self.safe)
    async def turn_off(self):
        self.events.append('OFF')
        return True


class FakeLease:
    def __init__(self, events, *, arm=True, disarm=True, renew_error=False, unhealthy=False):
        self.events, self.arm_ok, self.disarm_ok = events, arm, disarm
        self.renew_error, self.unhealthy = renew_error, unhealthy
        self.renewals = 0
    async def arm(self):
        self.events.append('lease arm')
        return self.arm_ok
    async def disarm(self):
        self.events.append('lease disarm')
        return self.disarm_ok
    async def renew_if_due(self):
        self.events.append('renew')
        self.renewals += 1
        if self.renew_error:
            raise RuntimeError('renew rejected')
        return SimpleNamespace(armed=not self.unhealthy, tripped=self.unhealthy,
            boot_quarantine=False, remaining_s=900, modbus_age_s=1)


class TransientTests(unittest.IsolatedAsyncioTestCase):
    async def test_intrinsic_psu_cutoff_is_55c_not_observed_38c(self):
        tx, _ = self.make()
        live = await tx.client.get_all_live()
        live['temp_int'] = 38.0
        tx._require_temperature(live, pre_enable=True)
        live['temp_int'] = 54.9
        tx._require_temperature(live, pre_enable=True)
        live['temp_int'] = 55.0
        with self.assertRaisesRegex(RuntimeError, '55 C intrinsic cutoff'):
            tx._require_temperature(live, pre_enable=True)

    def test_node_gate_requires_pinned_root_machine(self):
        with patch.object(transient.socket, 'gethostname', return_value='rd6018-bot'), \
             patch.object(transient.os, 'geteuid', return_value=0), \
             patch.object(transient.Path, 'read_text', return_value=transient._NODE104_MACHINE_ID):
            transient.require_node104()

        with patch.object(transient.socket, 'gethostname', return_value='wsl-host'), \
             patch.object(transient.os, 'geteuid', return_value=0), \
             patch.object(transient.Path, 'read_text', return_value=transient._NODE104_MACHINE_ID):
            with self.assertRaisesRegex(RuntimeError, 'exact node104'):
                transient.require_node104()

    def make(self, *, stop_error=False, stopped=True, sole=True, arm=True,
             enable=True, telemetry='on', disarm=True, independent=True,
             dwell_ready=True, sleep=None, protection=0, lease_renew_error=False,
             lease_unhealthy=False, lose_at=None, duration=10, lease=None, client=None,
             protection_age=1, protection_status='ok'):
        e = []
        async def stop():
            e.append('rollback armed')
            if stop_error: raise RuntimeError('stop failed')
            e.append('stop')
        async def verify(): e.append('verify stopped'); return stopped
        async def owner(): e.append('single owner'); return sole
        async def off(): e.append('independent OFF'); return independent
        async def restore(): e.append('restore')
        async def dwell(_): e.append('dwell')
        client = client or FakeClient(e, safe=enable, telemetry=telemetry,
            dwell_ready=dwell_ready, protection=protection, protection_age=protection_age,
            protection_status=protection_status, lose_at=lose_at)
        client.events = e
        lease = lease or FakeLease(e, arm=arm, disarm=disarm,
            renew_error=lease_renew_error, unhealthy=lease_unhealthy)
        tx = TransientAcceptance(client=client, lease=lease,
            stop_production=stop, verify_stopped=verify, prove_single_owner=owner,
            restore_production=restore, independent_off=off,
            target={'voltage_v': 14.4, 'current_a': .2, 'ovp_v': 15.0, 'ocp_a': .4},
            duration_s=duration, sleep=sleep or dwell)
        return tx, e

    async def test_rollback_armed_before_isolation_and_restore_after_off(self):
        tx, e = self.make()
        await tx.run()
        self.assertLess(e.index('rollback armed'), e.index('stop'))
        self.assertLess(e.index('independent OFF'), e.index('lease disarm'))
        self.assertLess(e.index('lease disarm'), e.index('restore'))

    async def test_service_stop_failure_still_attempts_off_without_restore(self):
        tx, e = self.make(stop_error=True)
        with self.assertRaisesRegex(RuntimeError, 'stop failed'): await tx.run()
        self.assertIn('OFF', e)
        self.assertIn('independent OFF', e)
        self.assertNotIn('restore', e)

    async def test_lease_failure_rolls_back(self):
        tx, e = self.make(arm=False)
        with self.assertRaisesRegex(RuntimeError, 'lease acquisition'): await tx.run()
        self.assertIn('OFF', e)
        self.assertIn('lease disarm', e)
        self.assertNotIn('enable', e)

    async def test_on_failure_rolls_back(self):
        tx, e = self.make(enable=False)
        with self.assertRaisesRegex(RuntimeError, 'safe enable'): await tx.run()
        self.assertIn('OFF', e)

    async def test_telemetry_loss_rolls_back(self):
        tx, e = self.make(telemetry='unavailable')
        with self.assertRaisesRegex(RuntimeError, 'telemetry'): await tx.run()
        self.assertIn('OFF', e)

    async def test_mid_window_telemetry_loss_rolls_back(self):
        tx, e = self.make(lose_at=4)
        with self.assertRaisesRegex(RuntimeError, 'telemetry lost'):
            await tx.run()
        self.assertIn('OFF', e)

    async def test_raw_protection_non_normal_rolls_back(self):
        tx, e = self.make(protection=2)
        with self.assertRaisesRegex(RuntimeError, 'not NORMAL'):
            await tx.run()
        self.assertIn('OFF', e)

    async def test_stale_protection_fails_before_enable(self):
        tx, e = self.make(protection_age=8.1)
        with self.assertRaisesRegex(RuntimeError, 'invalid or stale'):
            await tx.run()
        self.assertNotIn('enable', e)
        self.assertIn('OFF', e)

    async def test_non_ok_protection_fails_before_enable(self):
        tx, e = self.make(protection_status='unavailable')
        with self.assertRaisesRegex(RuntimeError, 'invalid or stale'):
            await tx.run()
        self.assertNotIn('enable', e)

    async def test_lease_renewal_failure_rolls_back(self):
        tx, e = self.make(lease_renew_error=True)
        with self.assertRaisesRegex(RuntimeError, 'renewal failed'):
            await tx.run()
        self.assertIn('OFF', e)

    async def test_unhealthy_watchdog_state_rolls_back(self):
        tx, e = self.make(lease_unhealthy=True)
        with self.assertRaisesRegex(RuntimeError, 'lease is unhealthy'):
            await tx.run()
        self.assertIn('OFF', e)

    async def test_900_second_window_is_monitored_and_renewed(self):
        ticks = []
        async def tick(_):
            ticks.append(1)
        tx, e = self.make(duration=900, sleep=tick)
        await tx.run()
        self.assertEqual(len(ticks), 900)
        self.assertEqual(e.count('renew'), 900)
        self.assertEqual(e.count('raw protection'), 903)

    async def test_live_guard_dwell_is_earned_from_fresh_reports_before_enable(self):
        from tools.acceptance_guard.guard import Guard
        clock = [0.0]
        guard = Guard(clock=lambda: clock[0])
        events = []
        client = FakeClient(events, safe=True, guard=guard)
        async def sleep(seconds):
            clock[0] += seconds
        tx, events = self.make(client=client, sleep=sleep)
        # The fake's reports are delivered to the same Guard used by the live adapter.
        client.guard = guard
        await tx.run()
        enable_at = events.index('enable')
        self.assertLess(events.index('raw protection'), enable_at)
        self.assertGreater(events.index('raw protection', enable_at), enable_at)
        self.assertGreaterEqual(clock[0], 12.0)

    async def test_dwell_uses_supplied_guarded_canonical_enable(self):
        tx, e = self.make()
        await tx.run()
        self.assertLess(e.index('lease arm'), e.index('enable'))
        self.assertLess(e.index('enable'), e.index('dwell'))

    async def test_dwell_rejection_fails_closed_before_output_enable(self):
        tx, e = self.make(dwell_ready=False)
        with self.assertRaisesRegex(RuntimeError, '12 second report dwell'):
            await tx.run()
        self.assertIn('OFF', e)
        self.assertIn('independent OFF', e)
        self.assertLess(e.index('independent OFF'), e.index('restore'))

    async def test_cancellation_runs_shielded_cleanup(self):
        entered = asyncio.Event()
        async def blocked(_):
            entered.set()
            await asyncio.Event().wait()
        tx, e = self.make(sleep=blocked)
        task = asyncio.create_task(tx.run())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertIn('OFF', e)
        self.assertIn('restore', e)

    async def test_final_off_mismatch_blocks_release_and_restore(self):
        tx, e = self.make(independent=False)
        self.assertFalse(await tx._cleanup())
        self.assertNotIn('lease disarm', e)
        self.assertNotIn('restore', e)

    async def test_final_off_mismatch_cannot_report_success(self):
        tx, e = self.make(independent=False)
        with self.assertRaisesRegex(RuntimeError, 'independent OFF proof'):
            await tx.run()
        self.assertNotIn('restore', e)

    async def test_dual_source_preflight_requires_both_fresh_sources_and_off(self):
        tx, e = self.make()
        await tx._fresh_off_preflight()
        original = tx.client.get_all_live
        async def stale_code():
            live = await original()
            live['_meta']['output_state_code_v2']['age_s'] = 8.1
            return live
        tx.client.get_all_live = stale_code
        with self.assertRaisesRegex(RuntimeError, 'dual-source'):
            await tx._fresh_off_preflight()
        self.assertNotIn('stop', e)

    async def test_stop_verification_failure_does_not_restore(self):
        tx, e = self.make(stopped=False)
        with self.assertRaisesRegex(RuntimeError, 'did not stop'): await tx.run()
        self.assertNotIn('restore', e)

    async def test_target_hard_caps_checked_before_isolation(self):
        tx, e = self.make()
        tx.target['voltage_v'] = 14.8
        with self.assertRaisesRegex(RuntimeError, 'ordinary authority'): await tx.run()
        self.assertNotIn('stop', e)

    async def test_contained_recovery_is_off_only_and_restores_after_release(self):
        tx, e = self.make()
        tx._production_stopped = True
        await tx.recover_contained()
        self.assertNotIn('enable', e)
        self.assertLess(e.index('raw protection'), e.index('lease arm'))
        self.assertLess(e.index('independent OFF'), e.index('lease disarm'))
        self.assertLess(e.index('lease disarm'), e.index('restore'))

    async def test_contained_recovery_preflight_failure_does_not_touch_lease_or_output(self):
        bad = FakeClient([], telemetry='on')
        bad.enabled = True
        tx, e = self.make(client=bad)
        tx.client.events = e
        with self.assertRaisesRegex(RuntimeError, 'requires Output OFF'):
            await tx.recover_contained()
        self.assertNotIn('lease arm', e)
        self.assertNotIn('OFF', e)
        self.assertNotIn('enable', e)

    async def test_contained_recovery_final_off_failure_keeps_service_contained(self):
        tx, e = self.make(independent=False)
        tx._production_stopped = True
        with self.assertRaisesRegex(RuntimeError, 'independent OFF proof'):
            await tx.recover_contained()
        self.assertNotIn('lease disarm', e)
        self.assertNotIn('restore', e)


    async def test_window_charges_slow_readback_and_renewal_to_elapsed_time(self):
        ticks = [0.0]
        events = []
        class SlowClient(FakeClient):
            async def get_all_live(self):
                if self.enabled:
                    ticks[0] += 0.7
                return await super().get_all_live()
        class SlowLease(FakeLease):
            async def renew_if_due(self):
                ticks[0] += 0.5
                return await super().renew_if_due()
        async def virtual_sleep(seconds):
            ticks[0] += seconds
        client = SlowClient(events)
        lease = SlowLease(events)
        tx, events = self.make(duration=20, client=client, lease=lease, sleep=virtual_sleep)
        tx.monotonic = lambda: ticks[0]
        self.assertTrue(await tx.run())
        self.assertGreaterEqual(ticks[0], 20.0)
        self.assertLess(ticks[0], 22.5)
        self.assertLess(events.count('renew'), 20)
        self.assertLess(events.index('independent OFF'), events.index('restore'))


if __name__ == '__main__': unittest.main()
