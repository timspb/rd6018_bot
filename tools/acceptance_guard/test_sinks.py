"""Fake backend/HTTP/native sink evidence against unchanged canonical methods."""
import asyncio
from types import SimpleNamespace as NS
import unittest

from tools.acceptance_guard.guard import Guard, Blocked, ordinary_off, fault_off
from tools.acceptance_guard.adapters import (GuardedHassClient, GuardedHAConnector,
    GuardedESPConnector, GuardedD061Control, GuardedNativeTransport, GuardedHATransport,
    GuardedRuntimeSafety)


class Clock:
    value = 100.0
    def __call__(self):
        return self.value


class SinkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = []
        self.clock = Clock()
        self.guard = Guard(clock=self.clock)
        calls = self.calls
        class Backend:
            async def enable_output(self): calls.append('ON')
            async def disable_output(self): calls.append('OFF')
            async def set_voltage(self, v): calls.append(('V', v))
        class Response:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        class Session:
            closed = False
            def post(self, url, **kwargs):
                calls.append((url.rsplit('/', 1)[-1], kwargs['json']))
                return Response()
        class Native:
            def switch_command(self, *args): calls.append(('switch', args))
            def number_command(self, *args): calls.append(('number', args))
        self.hass = GuardedHassClient('http://fake.invalid', 'fake', guard=self.guard, backend=Backend())
        self.ha = object.__new__(GuardedHAConnector)
        self.ha.guard = self.guard
        self.ha.transport = object.__new__(GuardedHATransport)
        self.ha.transport._session = Session()
        self.ha.transport.config = NS(entities={
            'control_output': 'fake.output', 'control_voltage': 'fake.voltage'},
            connection=NS(tls=False, host='fake.invalid', port=1))
        self.esp = object.__new__(GuardedESPConnector)
        self.esp.guard = self.guard
        self.esp.transport = object.__new__(GuardedNativeTransport)
        self.esp.transport.config = self.ha.transport.config
        self.esp.transport.client = Native()
        self.esp.transport.entities = [NS(object_id='fake.output', key=1, device_id=0),
                                     NS(object_id='fake.voltage', key=2, device_id=0)]

    def stable(self, state=False):
        for t in (100., 106., 112.):
            self.clock.value = t
            self.guard.observe(state, t)

    def seven(self):
        return [lambda: self.hass._switch_service('turn_on'),
                lambda: self.hass._switch_service('turn_off'),
                lambda: self.hass.set_voltage(15.51),
                self.ha.enable_output, lambda: self.ha.set_voltage(15.51),
                self.esp.enable_output, lambda: self.esp.set_voltage(15.51)]

    async def test_all_seven_original_canaries_zero_backend_calls(self):
        for n, route in enumerate(self.seven()):
            with self.subTest(route=n):
                with self.assertRaises(Blocked): await route()
                self.assertEqual(self.calls, [])

    async def test_premature_on_and_off_with_fresh_reports(self):
        for state in (False, True):
            self.guard.observe(state, 100.)
            self.clock.value = 106.
            self.guard.observe(state, 106.)
            for route in (lambda: self.hass._switch_service('turn_off' if state else 'turn_on'),
                          self.ha.disable_output if state else self.ha.enable_output,
                          self.esp.disable_output if state else self.esp.enable_output):
                with self.assertRaises(Blocked): await route()
            self.assertEqual(self.calls, [])
            self.clock.value = 100.
            self.guard = Guard(clock=self.clock)
            for item in (self.hass, self.ha, self.esp): item.guard = self.guard

    async def test_positive_each_output_sink_at_exact_12_seconds(self):
        for kind in ('hass', 'ha', 'esp'):
            self.guard = Guard(clock=self.clock)
            for item in (self.hass, self.ha, self.esp): item.guard = self.guard
            self.stable()
            item = getattr(self, kind)
            await (item._switch_service('turn_on') if kind == 'hass' else item.enable_output())
            self.assertEqual(len(self.calls), 1)
            self.assertIsNotNone(self.guard.pending)
            self.calls.clear()

    async def test_positive_voltage_each_sink_and_chemistry_ceiling(self):
        for item in (self.hass, self.ha, self.esp):
            await item.set_voltage(14.7)
            self.assertEqual(len(self.calls), 1)
            self.calls.clear()
            for value in (14.71, 15.5, 15.51, float('nan'), float('inf'), True, '14.7'):
                with self.assertRaises(Blocked): await item.set_voltage(value)
                self.assertEqual(self.calls, [])

    async def test_nested_hass_native_gate_dispatches_once(self):
        self.hass._physical_backend = self.esp
        self.stable()
        self.assertTrue(await self.hass._switch_service('turn_on'))
        self.assertEqual(len(self.calls), 1)

    async def test_stale_gapped_cached_future_and_backwards_evidence(self):
        for mode in ('stale', 'gap', 'cached', 'future', 'backwards', 'invalid'):
            self.clock.value = 100.
            self.guard = Guard(clock=self.clock)
            self.esp.guard = self.guard
            self.guard.observe(False, 100.)
            self.clock.value = 112.
            if mode == 'gap': self.guard.observe(False, 112.)
            elif mode == 'cached': self.guard.observe(False, 100.)
            elif mode == 'future': self.guard.observe(False, 120.)
            elif mode == 'invalid': self.guard.observe(False, 112., valid=False)
            elif mode == 'backwards': self.clock.value = 99.
            with self.assertRaises(Blocked): await self.esp.enable_output()
            self.assertEqual(self.calls, [])

    async def test_pending_not_cleared_by_old_state_gap_or_cached_ack(self):
        self.stable()
        await self.hass._switch_service('turn_on')
        self.calls.clear()
        for t, state in ((118., False), (140., False), (140., True)):
            self.clock.value = t
            self.guard.observe(state, t)
            self.assertIsNotNone(self.guard.pending)
        with self.assertRaises(Blocked): await self.hass.set_voltage(14.)
        with self.assertRaises(Blocked): await self.hass._switch_service('turn_off')
        self.assertEqual(self.calls, [])
        self.clock.value = 146.
        self.guard.observe(True, 146.)
        self.assertIsNone(self.guard.pending)
        with self.assertRaises(Blocked): await self.hass._switch_service('turn_off')

    async def test_failure_and_cancellation_leave_pending(self):
        for failure in (RuntimeError('ambiguous'), asyncio.CancelledError()):
            self.guard = Guard(clock=self.clock)
            self.stable()
            async def invoke(): raise failure
            with self.assertRaises(type(failure)):
                await self.guard.transition(True, invoke)
            self.assertIsNotNone(self.guard.pending)

    async def test_fault_off_no_clock_or_evidence_dependency(self):
        self.hass._physical_backend = self.esp
        # No telemetry dwell. Broken clock must never stop canonical OFF delivery.
        self.guard.clock = lambda: (_ for _ in ()).throw(OSError('evidence unavailable'))
        with fault_off():
            await self.hass._switch_service('turn_off')
        self.assertEqual(self.calls, [('switch', (1, False, 0))])
        self.assertTrue(self.guard.aborted)

    async def test_canonical_turn_off_is_immediate_and_ordinary_turn_off_blocked(self):
        # Fake verification only; real unchanged turn_off dispatch is exercised.
        class Client(GuardedHassClient):
            async def wait_for_output_off(self, **kwargs): return True
        client = Client(guard=self.guard, backend=self.hass._physical_backend)
        with ordinary_off():
            with self.assertRaises(Blocked): await client.turn_off()
        self.assertEqual(self.calls, [])
        self.guard.clock = lambda: (_ for _ in ()).throw(RuntimeError('clock fault'))
        self.assertTrue(await client.turn_off())
        self.assertEqual(self.calls, ['OFF'])

    async def test_d061_stop_rejects_before_coordinator_invocation(self):
        calls = self.calls
        class Coordinator:
            active = True
            async def verified_stop(self): calls.append('coordinator')
        control = GuardedD061Control(NS(rd_managed_live_adoption=Coordinator()), enabled=False)
        control.acceptance_guard = self.guard
        with self.assertRaises(Blocked): await control._verified_stop()
        self.assertEqual(self.calls, [])

    async def test_task_inheritance_cannot_reuse_inflight_permit(self):
        self.stable()
        async def outer():
            child = asyncio.create_task(self.esp.enable_output())
            with self.assertRaises(Blocked): await child
        await self.guard.transition(True, outer)
        self.assertEqual(self.calls, [])

    async def test_positive_ordinary_off_each_concrete_sink(self):
        for kind in ('hass', 'ha', 'esp'):
            self.guard = Guard(clock=self.clock)
            for item in (self.hass, self.ha, self.esp): item.guard = self.guard
            self.stable(True)
            item = getattr(self, kind)
            await (item._switch_service('turn_off') if kind == 'hass' else item.disable_output())
            self.assertEqual(len(self.calls), 1)
            self.calls.clear()

    async def test_fault_off_each_concrete_sink_immediate(self):
        for item in (self.ha, self.esp):
            self.guard.clock = lambda: (_ for _ in ()).throw(OSError('no clock'))
            with fault_off(): await item.disable_output()
            self.assertEqual(len(self.calls), 1)
            self.calls.clear()

    async def test_native_real_callback_earns_dwell_and_disconnect_invalidates(self):
        tr = self.esp.transport
        tr.guard = self.guard
        tr.config.entities['output_state'] = 'fake.output'
        SensorInfo = type('SensorInfo', (), {})
        SensorState = type('SensorState', (), {})
        entity = SensorInfo()
        entity.object_id, entity.key, entity.device_id = 'fake.output', 1, 0
        tr._entities_by_key = {1: [entity]}
        tr._state_cache, tr._state_updated_at, tr._state_reported_at, tr._state_types = {}, {}, {}, {}
        # Canonical callback uses time.monotonic; use its real times without sleeping.
        from unittest.mock import patch
        with patch('runtime.physical.transports.esp128.time.monotonic', self.clock):
            for t in (100., 106., 112.):
                self.clock.value = t
                callback = SensorState()
                callback.key, callback.state = 1, 0
                tr._on_state(callback)
            self.guard.require_transition(True)
            tr._on_connection_closed(None)
            with self.assertRaises(Blocked): self.guard.require_transition(True)

    async def test_default_cap_155_and_tighter_policy_remains(self):
        for cap, allowed in ((16.5, 15.5), (14.4, 14.4)):
            guard = Guard(clock=self.clock, voltage_ceiling=cap)
            guard.voltage(allowed)
            with self.assertRaises(Blocked): guard.voltage(allowed + .01)

    async def test_false_delivery_stays_pending(self):
        self.stable()
        async def failure(): return False
        self.assertFalse(await self.guard.transition(True, failure))
        self.assertIsNotNone(self.guard.pending)

    async def test_delayed_reports_cannot_backdate_observed_dwell(self):
        for arrival, report in ((100., 93.), (106., 99.), (112., 105.)):
            self.clock.value = arrival
            self.guard.observe(False, report)
        with self.assertRaises(Blocked): await self.esp.enable_output()
        self.assertEqual(self.calls, [])
        self.clock.value = 119.
        self.guard.observe(False, 112.)
        await self.esp.enable_output()
        self.assertEqual(len(self.calls), 1)

    async def test_observation_outage_does_not_credit_contiguous_delayed_sources(self):
        for arrival, report in ((100., 100.), (113., 106.), (114., 112.)):
            self.clock.value = arrival
            self.guard.observe(False, report)
        with self.assertRaises(Blocked): await self.esp.enable_output()
        self.assertEqual(self.calls, [])

    async def test_canonical_runtime_ordinary_stop_rejects_before_off_owner(self):
        owner = object.__new__(GuardedRuntimeSafety)
        owner.acceptance_guard = self.guard
        # Missing canonical fields prove it rejected before original shutdown.
        with ordinary_off():
            with self.assertRaises(Blocked): await owner.turn_off()
        self.assertEqual(self.calls, [])

    async def test_real_runtime_fault_off_ignores_ordinary_scope_and_bad_guard_clock(self):
        class Client(GuardedHassClient):
            async def wait_for_output_off(inner, **kwargs): return True
        client = Client(guard=self.guard, backend=self.hass._physical_backend)
        owner = object.__new__(GuardedRuntimeSafety)
        owner.acceptance_guard = self.guard
        owner._off_lock = asyncio.Lock()
        async def raw_live(): raise OSError('telemetry unavailable')
        async def verified(**kwargs): return True
        owner._raw_live = raw_live
        owner._raw_turn_off = client.turn_off
        owner._verify_switch_off = verified
        self.guard.pending = (True, 100.)
        self.guard.clock = lambda: (_ for _ in ()).throw(OSError('bad clock'))
        with ordinary_off():
            self.assertTrue(await owner._ensure_output_off('runtime thermal fault'))
        self.assertEqual(self.calls, ['OFF'])
        self.assertTrue(self.guard.aborted)

    async def test_fake_hass_http_fallback_also_cannot_bypass_sink(self):
        client = GuardedHassClient('http://fake.invalid', 'fake', guard=self.guard)
        async def unexpected_session():
            self.calls.append('HTTP session')
            raise AssertionError('premature I/O')
        client._ensure_session = unexpected_session
        for route in (lambda: client._switch_service('turn_on'),
                      lambda: client._switch_service('turn_off'),
                      lambda: client.set_voltage(15.51)):
            with self.assertRaises(Blocked): await route()
        self.assertEqual(self.calls, [])

    async def test_tampered_pairing_manifest_fails_before_any_import_or_bind(self):
        from tools.acceptance_guard.pairing import assemble
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'
            manifest.write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'untrusted'):
                assemble(directory, manifest)

    async def test_invalid_chemistry_cap_is_not_normalized_into_authority(self):
        for cap in (float('nan'), float('inf'), -1., 0., True, '14.7'):
            with self.assertRaises(ValueError): Guard(voltage_ceiling=cap)

    async def test_real_runtime_positive_ordinary_stop_retains_canonical_verification(self):
        class Client(GuardedHassClient):
            async def wait_for_output_off(inner, **kwargs): return True
        class Owner(GuardedRuntimeSafety):
            async def _disarm_edge_lease_best_effort(inner): self.calls.append('lease verification')
        client = Client(guard=self.guard, backend=self.hass._physical_backend)
        owner = object.__new__(Owner)
        owner.acceptance_guard = self.guard
        owner._off_lock = asyncio.Lock()
        async def raw_live(): return {'switch': 'on'}
        async def verified(**kwargs):
            self.calls.append('OFF verification')
            return True
        owner._raw_live = raw_live
        owner._raw_turn_off = client.turn_off
        owner._verify_switch_off = verified
        self.stable(True)
        with ordinary_off():
            self.assertTrue(await owner.turn_off())
        self.assertEqual(self.calls, ['OFF', 'OFF verification', 'lease verification'])
        self.assertFalse(self.guard.aborted)

    async def test_safe_enable_failure_rollback_is_immediate_even_via_runtime_owner(self):
        from unittest.mock import patch
        from tools.acceptance_guard.guard import is_fault_off
        class Coordinator:
            def __init__(inner, adapter, *args, **kwargs): inner.adapter = adapter
            async def enable(inner, request):
                self.assertTrue(is_fault_off())
                return await inner.adapter.turn_off()
        class Client(GuardedHassClient):
            async def wait_for_output_off(inner, **kwargs): return True
        class Owner(GuardedRuntimeSafety):
            async def _disarm_edge_lease_best_effort(inner): pass
        client = Client(guard=self.guard, backend=self.hass._physical_backend)
        raw_off = client.turn_off
        owner = object.__new__(Owner)
        owner.acceptance_guard = self.guard
        owner._off_lock = asyncio.Lock()
        async def raw_live(): raise OSError('no telemetry')
        async def verified(**kwargs): return True
        owner._raw_live, owner._raw_turn_off, owner._verify_switch_off = raw_live, raw_off, verified
        client.turn_off = owner.turn_off  # Mirrors canonical owner install(), in test only.
        self.guard.clock = lambda: (_ for _ in ()).throw(OSError('clock unavailable'))
        with patch('hass_api.SafeOutputCoordinator', Coordinator):
            self.assertTrue(await client.safe_enable_output(voltage_v=14.,current_a=.1,
                ovp_v=14.5,ocp_a=.2,recipe_voltage_ceiling_v=14.7))
        self.assertEqual(self.calls, ['OFF'])
        self.assertTrue(self.guard.aborted)

    async def test_monitored_updates_cannot_dispatch_unclassified_operator_mutations(self):
        from tools.acceptance_guard.adapters import AcceptanceUpdatesOnly
        async def handler(*args): self.calls.append('unclassified handler')
        await AcceptanceUpdatesOnly()(handler, NS(), {})
        self.assertEqual(self.calls, [])

    async def test_actual_d061_fault_cleanup_delegates_immediate_canonical_off(self):
        from unittest.mock import patch
        from rd_managed_adoption import ManagedLiveAdoptionCoordinator
        class Client(GuardedHassClient):
            async def wait_for_output_off(inner, **kwargs): return True
        class Owner(GuardedRuntimeSafety):
            async def _disarm_edge_lease_best_effort(inner): pass
        client = Client(guard=self.guard, backend=self.hass._physical_backend)
        owner = object.__new__(Owner)
        owner.acceptance_guard = self.guard
        owner._off_lock = asyncio.Lock()
        async def raw_live(): raise OSError('fault telemetry unavailable')
        async def verified(**kwargs): return True
        owner._raw_live, owner._raw_turn_off, owner._verify_switch_off = raw_live, client.turn_off, verified
        coordinator = object.__new__(ManagedLiveAdoptionCoordinator)
        coordinator.app = NS()
        coordinator.manager = NS(hands_off=False)
        coordinator.guard = NS(edge_safety_lease=None)
        coordinator._persist = lambda: None
        coordinator._retire_manual_software = lambda *a, **kw: None
        self.guard.pending = (True, 100.)
        self.guard.clock = lambda: (_ for _ in ()).throw(OSError('clock fault'))
        with patch('rd_managed_adoption.get_or_create_execution_port',
                   return_value=NS(request_verified_off=owner.turn_off)):
            self.assertTrue(await coordinator._verified_off('ambiguous edge adoption'))
        self.assertEqual(self.calls, ['OFF'])
        self.assertTrue(self.guard.aborted)

    async def test_pairing_refuses_live_production_even_if_caller_claims_ready(self):
        from unittest.mock import patch
        from tools.acceptance_guard.pairing import run_prepared
        with patch('tools.acceptance_guard.pairing.subprocess.check_output',
                   return_value='ActiveState=active\nMainPID=36789\n'), \
             patch('tools.acceptance_guard.pairing.assemble') as assemble:
            with self.assertRaisesRegex(RuntimeError, 'production must be stopped'):
                await run_prepared('/no/source','/no/manifest',physical_ready=True,sole_poller_ready=True)
            assemble.assert_not_called()

    async def test_pairing_missing_physical_readiness_cannot_start_lifecycle(self):
        from unittest.mock import patch
        from tools.acceptance_guard.pairing import run_prepared
        with patch('tools.acceptance_guard.pairing.assemble') as assemble:
            with self.assertRaisesRegex(RuntimeError, 'physical supervision'):
                await run_prepared('/no/source','/no/manifest',physical_ready=False,sole_poller_ready=True)
            assemble.assert_not_called()

    async def test_transaction_above_acceptance_cap_cannot_program_any_backend(self):
        with self.assertRaises(Blocked):
            await self.hass.safe_enable_output(voltage_v=15.51,current_a=.1,
                ovp_v=16.,ocp_a=.2,recipe_voltage_ceiling_v=17.5)
        self.assertEqual(self.calls, [])

    async def test_d061_fault_dispatch_keeps_hands_off_containment_immediate(self):
        class Control(GuardedD061Control):
            async def _fault_ambiguous_edge_ack(inner, battery_id):
                await self.ha.disable_output()
                return {'contained':True}
            async def _adopt_battery(inner, battery_id):
                await self.esp.disable_output()  # Only synthetic failure cleanup.
                return {'contained':True}
        control = Control(NS(),enabled=False)
        self.guard.clock = lambda: (_ for _ in ()).throw(OSError('clock unavailable'))
        for op in ('d061_fault_ambiguous_edge_ack','d061_adopt_battery'):
            response = await control.dispatch({'op':op,'battery_id':'Leoch_72Ah'})
            self.assertTrue(response['ok'],response)
            self.assertEqual(len(self.calls),1)
            self.calls.clear()

    async def test_second_acceptance_launch_is_blocked_by_os_poller_lock(self):
        from unittest.mock import patch
        from tools.acceptance_guard.pairing import run_prepared
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / 'state'
            state.mkdir()
            with patch('tools.acceptance_guard.pairing.subprocess.check_output',
                       return_value='ActiveState=inactive\nMainPID=0\n'), \
                 patch('tools.acceptance_guard.pairing.Path.iterdir',return_value=[]), \
                 patch('tools.acceptance_guard.pairing.Path.cwd',return_value=state), \
                 patch('tools.acceptance_guard.pairing.fcntl.flock',side_effect=BlockingIOError()), \
                 patch('tools.acceptance_guard.pairing.assemble') as assemble:
                with self.assertRaisesRegex(RuntimeError,'poller lock'):
                    await run_prepared(root/'source',root/'manifest',physical_ready=True,sole_poller_ready=True)
                assemble.assert_not_called()

    async def test_pairing_uses_deferred_bind_without_replacing_methods(self):
        from tools.acceptance_guard.pairing import bind_client
        from runtime.config import load_config
        from pathlib import Path
        import hass_api
        calls = []
        class Deferred:
            is_bound = False
            def bind(self, client): calls.append(client)
        original = hass_api.HassClient._switch_service
        config = load_config(Path(hass_api.__file__).parent / 'config')
        guard, client = bind_client(NS(hass=Deferred()), config, base_url='http://fake.invalid', token='fake')
        self.assertIs(hass_api.HassClient._switch_service, original)
        self.assertIs(client, calls[0])
        self.assertIs(client.guard, client._physical_backend.guard)
        self.assertEqual(guard.voltage_ceiling, 14.7)

    async def test_d061_positive_stop_runs_canonical_operation_with_ordinary_scope(self):
        calls = self.calls
        class Coordinator:
            active = True
            async def verified_stop(inner):
                calls.append('coordinator')
                await self.hass._switch_service('turn_off')
                return True
        class Control(GuardedD061Control):
            async def _raw_live(inner): return {'switch': 'off', 'output_state_code_v2': 0}
        control = Control(NS(rd_managed_live_adoption=Coordinator()), enabled=False)
        control.acceptance_guard = self.guard
        self.stable(True)
        self.assertTrue((await control._verified_stop())['stopped'])
        self.assertEqual(self.calls, ['coordinator', 'OFF'])

    async def test_d061_original_off_retries_do_not_wait_or_reauthorize(self):
        calls = self.calls
        class Coordinator:
            active = True
            async def verified_stop(inner):
                await self.hass._switch_service('turn_off')
                self.guard.clock = lambda: (_ for _ in ()).throw(OSError('clock lost'))
                await self.hass._switch_service('turn_off')
                return True
        class Control(GuardedD061Control):
            async def _raw_live(inner): return {'switch': 'off', 'output_state_code_v2': 0}
        control = Control(NS(rd_managed_live_adoption=Coordinator()), enabled=False)
        control.acceptance_guard = self.guard
        self.stable(True)
        self.assertTrue((await control._verified_stop())['stopped'])
        self.assertEqual(calls, ['OFF', 'OFF'])

    async def test_original_turn_on_postverification_failure_off_is_immediate(self):
        from unittest.mock import patch
        class Client(GuardedHassClient):
            def _recent_programming_request(inner): return NS()
            async def get_all_live(inner): return {}
        class Coordinator:
            def __init__(inner, *args): pass
            async def confirm_programmed_readback(inner, request): return None, NS(allowed=True)
        client = Client(guard=self.guard, backend=self.hass._physical_backend)
        client._safety_supervisor = NS(preflight=lambda *a: NS(allowed=True),
            verify_live_output=lambda *a: NS(allowed=False, detail='synthetic post-enable rejection'))
        self.stable()
        with patch('hass_api.snapshot_from_live', return_value=NS(output_on=True)), \
             patch('hass_api.SafeOutputCoordinator', Coordinator):
            self.assertFalse(await client.turn_on())
        self.assertEqual(self.calls, ['ON', 'OFF'])
        self.assertTrue(self.guard.aborted)

    async def test_ha_actual_get_requires_advancing_last_reported(self):
        from unittest.mock import patch
        tr = self.ha.transport
        tr.guard = self.guard
        tr.config.entities['output_state'] = 'fake.output'
        class Response:
            status = 200
            async def __aenter__(inner): return inner
            async def __aexit__(inner, *a): pass
            async def json(inner): return data
        class Session:
            closed = False
            def get(inner, *a, **kw): return Response()
        tr._session = Session()
        for t in (100., 106., 112.):
            self.clock.value = t
            data = {'state': '0', 'last_reported': '1970-01-01T00:01:40+00:00'}
            with patch('tools.acceptance_guard.adapters.time.time', self.clock):
                await tr._get('fake.output')
        with self.assertRaises(Blocked): self.guard.require_transition(True)
        for t in (112., 118., 124.):
            self.clock.value = t
            from datetime import datetime, timezone
            data = {'state': '0', 'last_reported': datetime.fromtimestamp(t, timezone.utc).isoformat()}
            with patch('tools.acceptance_guard.adapters.time.time', self.clock):
                await tr._get('fake.output')
        self.guard.require_transition(True)


if __name__ == '__main__':
    unittest.main()
