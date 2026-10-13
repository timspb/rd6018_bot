"""Hardware-inert D061 regressions from physical 2026-10-13 OFF_PENDING."""
import asyncio
import unittest

from tests import test_d061_takeover_smoke as fixtures


class OffPendingRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        tx, events, client = fixtures.TakeoverTests.make(self, adopted_status=True)
        state = {'recovered': False}
        original_control = tx.control

        async def control(op, **kwargs):
            if op == 'd061_verified_stop':
                events.append(('d061_verified_stop', kwargs))
                client.enabled = False
                return {'ok': True, 'operation': op,
                        'result': {'stopped': False, 'output': 'off'}}
            if op == 'status':
                events.append(('status', kwargs))
                return {'ok': True, 'result': {
                    'rd_control_mode': 'pb_managed',
                    'adoption_state': 'interrupted' if state['recovered'] else 'off_pending',
                    'manual_state': 'failed' if state['recovered'] else 'active',
                    'output': 'off' if not client.enabled else 'on',
                    'output_state_code_v2': 0 if not client.enabled else 1,
                }}
            return await original_control(op, **kwargs)

        tx.control = control
        return tx, events, client, state

    async def test_off_pending_only_canonical_recovery_after_off_and_disarm(self):
        tx, events, _, state = self.make()

        async def canonical_off_only_recovery():
            events.append('canonical off_pending recovery')
            state['recovered'] = True
            return True

        tx.recover_off_pending = canonical_off_only_recovery
        with self.assertRaisesRegex(RuntimeError, 'stop failed or incomplete'):
            await tx.run()
        self.assertEqual(tx.evidence['off_pending_recovery'], {'acknowledged': True})
        self.assertTrue(tx.output_off_proven)
        self.assertTrue(tx.lease_disarmed)
        self.assertTrue(tx.ownership_safe)
        self.assertTrue(tx.acceptance_stopped)
        self.assertTrue(tx.restored)
        self.assertTrue(tx._cleanup_complete)
        self.assertLess(events.index('independent OFF'), events.index('canonical off_pending recovery'))
        self.assertLess(events.index('lease disarm'), events.index('canonical off_pending recovery'))
        self.assertLess(events.index('canonical off_pending recovery'), events.index('restore production'))

    async def test_off_pending_recovery_failure_never_restores(self):
        tx, events, _, _ = self.make()
        async def fails():
            events.append('failed recovery')
            return False
        tx.recover_off_pending = fails
        with self.assertRaisesRegex(RuntimeError, 'containment is unresolved'):
            await tx.run()
        self.assertFalse(tx.ownership_safe)
        self.assertFalse(tx.restored)
        self.assertIn('failed recovery', events)
        self.assertNotIn('restore production', events)

    async def test_no_recovery_when_independent_off_is_lost(self):
        tx, events, _, _ = self.make()
        calls = [0]
        async def independent():
            calls[0] += 1
            # Preflight only; all post-stop readback is unavailable.
            return calls[0] == 1
        tx.independent_off = independent
        async def should_not_run():
            events.append('unsafe recovery')
            return True
        tx.recover_off_pending = should_not_run
        with self.assertRaisesRegex(RuntimeError, 'containment is unresolved'):
            await tx.run()
        self.assertNotIn('unsafe recovery', events)
        self.assertNotIn('restore production', events)


if __name__ == '__main__':
    unittest.main()
