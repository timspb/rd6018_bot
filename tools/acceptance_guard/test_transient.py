import asyncio
import unittest
from types import SimpleNamespace as NS

from tools.acceptance_guard.transient import TransientAcceptance


class Client:
    def __init__(self): self.live_calls = 0; self.output = 'off'
    async def get_all_live(self):
        self.live_calls += 1
        # Safety preflight now requires distinct fresh PSU/block and battery
        # thermometers plus raw NORMAL protection on *every* sample.
        return {'switch': self.output, 'output_state_code_v2': int(self.output == 'on'),
                'protection_code': 0, 'temp_int': 30.0, 'temp_ext': 24.0,
                '_meta': {k: {'status': 'ok', 'age_s': 0}
                    for k in ('switch', 'output_state_code_v2', 'protection_code',
                              'temp_int', 'temp_ext')}}
    async def safe_enable_output(self, **kw): self.output = 'on'; return NS(enabled=True)
    async def turn_off(self): self.output = 'off'


class Lease:
    config = NS(lease_ttl_s=900)
    async def arm(self): return True
    async def renew_if_due(self): return NS(armed=True, tripped=False, boot_quarantine=False,
                                             remaining_s=900, modbus_age_s=0)
    async def disarm(self): return True


class TransientCleanupTests(unittest.IsolatedAsyncioTestCase):
    def make(self, *, off=None, disarm=None, restore=None):
        state = {'off': off, 'disarm': disarm, 'restore': restore}
        client, lease = Client(), Lease()
        async def independent():
            value = state['off']() if callable(state['off']) else (True if state['off'] is None else state['off'])
            return await value if asyncio.iscoroutine(value) else value
        async def disarm_fn():
            if callable(state['disarm']): return state['disarm']()
            return True if state['disarm'] is None else state['disarm']
        lease.disarm = disarm_fn
        async def stop(): pass
        async def verify(): return True
        async def owner(): return True
        async def restore_fn():
            if callable(state['restore']): return await state['restore']()
            if state['restore'] is False: raise RuntimeError('restore fault')
        tx = TransientAcceptance(client=client, lease=lease, stop_production=stop,
            verify_stopped=verify, prove_single_owner=owner, restore_production=restore_fn,
            independent_off=independent, target={'voltage_v': 13.8, 'current_a': 1,
            'ovp_v': 15, 'ocp_a': 2}, duration_s=.01, sleep=lambda _: asyncio.sleep(0))
        tx._wait_for_ordinary_on_dwell = lambda: asyncio.sleep(0)
        return tx, state

    async def test_off_mismatch_fails_run_and_retry_recovers(self):
        tx, state = self.make(off=False)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            await tx.run()
        self.assertFalse(tx._cleaned)
        state['off'] = True
        self.assertTrue(await tx._cleanup())

    async def test_disarm_failure_fails_run_and_retry_recovers(self):
        tx, state = self.make(disarm=False)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            await tx.run()
        state['disarm'] = True
        self.assertTrue(await tx._cleanup())

    async def test_restore_failure_fails_run_and_retry_recovers(self):
        tx, state = self.make(restore=False)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            await tx.run()
        state['restore'] = None
        self.assertTrue(await tx._cleanup())

    async def test_cancellation_during_cleanup_remains_recoverable(self):
        entered = asyncio.Event(); release = asyncio.Event()
        async def delayed_off():
            entered.set(); await release.wait(); return True
        tx, _ = self.make(off=delayed_off)
        tx._rollback_armed = True
        tx._production_stopped = True
        tx._lease_attempted = True
        task = asyncio.create_task(tx._cleanup())
        await entered.wait()
        async def wait_shielded(): return await asyncio.shield(task)
        waiter = asyncio.create_task(wait_shielded())
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError): await waiter
        release.set()
        await task
        self.assertTrue(tx._cleaned)
        self.assertTrue(await tx._cleanup())

    async def test_failed_cleanup_never_restores_production(self):
        tx, _ = self.make(off=False)
        tx._production_stopped = True
        tx._lease_attempted = True
        self.assertFalse(await tx._cleanup())
        self.assertFalse(tx._restored)
        self.assertIn('OFF proof', tx._cleanup_error)
