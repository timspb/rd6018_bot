import asyncio
import contextlib
import io
import json
import unittest
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.acceptance_guard.takeover import D061TakeoverSmoke, TARGET, fingerprint_matches, independent_output_off, select_leoch_battery
from tools.acceptance_guard.takeover import seed_isolated_hands_off_state, require_hands_off_manager
from tools import run_d061_takeover_smoke as runner
from rd_control_mode import RdControlMode, RdControlModeManager
from managed_runtime_safety import ManagedRuntimeSafetyGuard


class _TestManagedGuard(ManagedRuntimeSafetyGuard):
    pass


def _manager(path):
    app = SimpleNamespace(runtime_safety_guard=_TestManagedGuard.__new__(_TestManagedGuard))
    return RdControlModeManager(app, state_file=str(path))


class D061BootstrapOrderTests(unittest.TestCase):
    def test_missing_state_instantiates_pb_managed_before_fix_order(self):
        with __import__('tempfile').TemporaryDirectory() as directory:
            manager = _manager(Path(directory) / 'rd_control_mode_v2.json')
            self.assertIs(manager.mode, RdControlMode.PB_MANAGED)
            self.assertFalse(manager.hands_off)

    def test_seed_before_assembly_instantiates_and_asserts_hands_off(self):
        with __import__('tempfile').TemporaryDirectory() as directory:
            isolated = Path(directory) / 'stage' / 'state'
            state_path = seed_isolated_hands_off_state(isolated)
            manager = _manager(state_path)
            self.assertIs(require_hands_off_manager(manager), manager)
            self.assertIs(manager.mode, RdControlMode.HANDS_OFF)

    def test_corrupt_state_fails_closed_to_pb_managed(self):
        with __import__('tempfile').TemporaryDirectory() as directory:
            state_path = Path(directory) / 'rd_control_mode_v2.json'
            state_path.write_text('{broken', encoding='utf-8')
            manager = _manager(state_path)
            self.assertIs(manager.mode, RdControlMode.PB_MANAGED)
            self.assertFalse(manager.persistence_ok)
            with self.assertRaisesRegex(RuntimeError, 'not HANDS_OFF'):
                require_hands_off_manager(manager)

    def test_seed_writes_only_isolated_state(self):
        with __import__('tempfile').TemporaryDirectory() as directory:
            root = Path(directory)
            production = root / 'production' / 'rd_control_mode_v2.json'
            production.parent.mkdir()
            production.write_text('production-sentinel', encoding='utf-8')
            isolated = root / 'stage' / 'state'
            seed_isolated_hands_off_state(isolated)
            self.assertEqual(production.read_text(encoding='utf-8'), 'production-sentinel')
            self.assertEqual(json.loads((isolated / 'rd_control_mode_v2.json').read_text()),
                             {'version': 1, 'mode': 'hands_off'})


class Lease:
    def __init__(self, events, *, release_ok=True):
        self.events = events
        self.release_ok = release_ok
        self.renewals_suspended = False
        self.armed = False
        self.generation = 4
    async def arm(self):
        self.events.append('lease arm')
        self.armed = True
        return True
    async def read_state(self):
        self.events.append('read lease')
        return SimpleNamespace(armed=self.armed, tripped=False,
                               boot_quarantine=False, modbus_age_s=1,
                               generation=self.generation, remaining_s=0)
    def suspend_renewals(self):
        self.events.append('suspend renewals')
        self.renewals_suspended = True
    async def prepare_hands_off_release(self):
        self.events.append('prepare release')
        assert self.renewals_suspended
        return SimpleNamespace(generation=4)
    async def release_to_hands_off(self, *, expected_generation):
        self.events.append(('release', expected_generation))
        if not self.release_ok:
            raise RuntimeError('release acknowledgement failed')
        self.armed = False
        self.generation += 1
        return SimpleNamespace(armed=False, generation=self.generation)
    async def disarm(self):
        self.events.append('lease disarm')
        self.armed = False
        return True


class Client:
    def __init__(self, events, *, enable_ok=True):
        self.events = events
        self.enable_ok = enable_ok
        self.enabled = False
        self.setpoints = dict(TARGET)
        self.guard = SimpleNamespace(require_transition=lambda _target: None)
    async def get_all_live(self):
        self.events.append('read live')
        state = 'on' if self.enabled else 'off'
        return {'switch': state, 'output_state_code_v2': 1 if self.enabled else 0,
                'voltage': 0.0 if not self.enabled else 13.2,
                'current': 0.0 if not self.enabled else 0.1,
                'protection_code': 0.0,
                'set_voltage_readback_v2': self.setpoints['voltage_v'],
                'set_current_readback_v2': self.setpoints['current_a'],
                'ovp_readback_v2': self.setpoints['ovp_v'],
                'ocp_readback_v2': self.setpoints['ocp_a'],
                'temp_int': 30.0, 'temp_ext': 24.0,
                '_meta': {key: {'status': 'ok', 'age_s': 1}
                          for key in ('switch', 'output_state_code_v2', 'voltage', 'current',
                              'protection_code', 'set_voltage_readback_v2',
                              'set_current_readback_v2', 'ovp_readback_v2',
                              'ocp_readback_v2', 'temp_int', 'temp_ext')}}
    async def safe_enable_output(self, **kwargs):
        self.events.append(('safe enable', kwargs))
        self.setpoints = {key: kwargs[key] for key in TARGET}
        self.enabled = self.enable_ok
        return SimpleNamespace(enabled=self.enable_ok)
    async def turn_off(self):
        self.events.append('canonical off')
        self.enabled = False
        return True


class TakeoverTests(unittest.IsolatedAsyncioTestCase):
    def make(self, *, release_ok=True, adoption_ok=True, state_ok=True, stop_ok=True,
             adopted_status=False):
        events = []
        clock = [0.0]
        client = Client(events)
        lease = Lease(events, release_ok=release_ok)
        lifecycle = {'adoption_state': 'failed', 'manual_state': 'stopped'}
        async def record(name, value=True):
            events.append(name)
            return value
        async def control(op, **kwargs):
            events.append((op, kwargs))
            if op == 'status':
                return {'ok': True, 'result': {
                    'rd_control_mode': 'pb_managed', **lifecycle,
                    'output': 'on' if client.enabled else 'off',
                    'output_state_code_v2': 1 if client.enabled else 0}}
            if op == 'd061_verified_stop':
                if stop_ok:
                    client.enabled = False
                    lifecycle.update(adoption_state='completed', manual_state='stopped')
            if op == 'd061_adopt_battery':
                if adoption_ok and adopted_status:
                    lifecycle.update(adoption_state='active', manual_state='active')
                return ({'ok': True, 'result': {'adopted': True}} if adoption_ok else
                        {'ok': False, 'error': {'code': 'ADOPTION_REJECTED', 'detail': 'test'}})
            if op == 'd061_verified_stop':
                return ({'ok': True, 'result': {'stopped': True, 'output': 'off'}} if stop_ok else
                        {'ok': False, 'error': {'code': 'STOP_REJECTED', 'detail': 'test'}})
            return {'ok': True}
        async def verify(target):
            events.append(('verify state', dict(target)))
            return state_ok and client.setpoints == TARGET
        tx = D061TakeoverSmoke(
            client=client, lease=lease,
            stop_production=lambda: record('stop production'),
            verify_stopped=lambda: record('verify stopped'),
            bootstrap_hands_off=lambda: record('bootstrap HANDS_OFF'),
            start_acceptance=lambda: record('start guarded composition'),
            control=control,
            locate_battery=lambda name: record('locate ' + name, 'leoch_id_from_registry'),
            verify_state=verify,
            stop_acceptance=lambda: record('stop acceptance'),
            independent_off=lambda: record('independent OFF', not client.enabled),
            restore_production=lambda: record('restore production'),
            sleep=lambda seconds: (clock.__setitem__(0, clock[0] + seconds), record('monitor second'))[1],
            monotonic=lambda: clock[0],
        )
        return tx, events, client

    async def test_intrinsic_psu_cutoff_is_55c_not_observed_38c(self):
        tx, _, client = self.make()
        live = await client.get_all_live()
        live['temp_int'] = 38.0
        self.assertTrue(tx._temperature_ok(live, pre_enable=True))
        live['temp_int'] = 54.9
        self.assertTrue(tx._temperature_ok(live, pre_enable=True))
        live['temp_int'] = 55.0
        self.assertFalse(tx._temperature_ok(live, pre_enable=True))

    def test_fingerprint_accepts_raw_binary_readbacks_within_tolerance(self):
        raw = {'set_voltage_v': 13.569999694824219,
               'set_current_a': 0.09999999403953552,
               'ovp_v': 14.069999694824219,
               'ocp_a': 0.19999998807907104}
        self.assertTrue(fingerprint_matches(raw, TARGET))

    def test_fingerprint_rejects_mismatch_nonfinite_bool_and_missing(self):
        base = {'set_voltage_v': 13.57, 'set_current_a': .1, 'ovp_v': 14.07, 'ocp_a': .2}
        for bad in ({**base, 'set_voltage_v': 13.5901},
                    {**base, 'set_voltage_v': float('nan')},
                    {**base, 'set_voltage_v': True},
                    {key: value for key, value in base.items() if key != 'ocp_a'}):
            with self.subTest(bad=bad):
                self.assertFalse(fingerprint_matches(bad, TARGET))

    async def test_preflight_requires_zero_output_normal_protection_and_target_fingerprint(self):
        tx, _, client = self.make()
        await tx._fresh_off()
        live = await client.get_all_live()
        live['protection_code'] = 1
        client.get_all_live = lambda: asyncio.sleep(0, result=live)
        with self.assertRaisesRegex(RuntimeError, 'raw protection NORMAL'):
            await tx._fresh_off()
        live['protection_code'] = 0
        live['set_voltage_readback_v2'] = 13.6
        with self.assertRaisesRegex(RuntimeError, 'fingerprint mismatch'):
            await tx._fresh_off()

    async def test_handoff_order_typed_adoption_stop_and_setpoints(self):
        tx, events, client = self.make()
        self.assertTrue(await tx.run())
        ordered = ['read live', 'independent OFF', 'read lease', 'stop production', 'verify stopped', 'lease arm',
                   'safe enable', 'suspend renewals', 'prepare release',
                   'bootstrap HANDS_OFF', 'start guarded composition']
        positions = [next(i for i, event in enumerate(events)
                          if event == name or (isinstance(event, tuple) and event[0] == name))
                     for name in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(events.count('monitor second'), 20)
        self.assertIn(('d061_adopt_battery', {'battery_id': 'leoch_id_from_registry'}), events)
        self.assertIn(('d061_verified_stop', {}), events)
        self.assertEqual(client.setpoints, TARGET)
        self.assertLess(events.index('independent OFF'), events.index('restore production'))

    async def test_false_off_preflight_prevents_all_ownership_changes(self):
        tx, events, _ = self.make()
        tx.independent_off = lambda: asyncio.sleep(0, result=1)
        with self.assertRaisesRegex(RuntimeError, 'preflight requires fresh independent'):
            await tx.run()
        self.assertNotIn('lease disarm', events)
        self.assertNotIn('stop production', events)
        self.assertNotIn('restore production', events)

    async def test_false_post_stop_off_proof_never_returns_pass_or_restarts(self):
        tx, events, _ = self.make()
        calls = [0]
        async def off_proof():
            calls[0] += 1
            events.append('independent OFF proof ' + str(calls[0]))
            return calls[0] == 1
        tx.independent_off = off_proof
        with self.assertRaisesRegex(RuntimeError, 'independent OFF proof failed'):
            await tx.run()
        self.assertNotIn('restore production', events)

    async def test_stop_is_not_followed_by_restart_when_stop_verification_fails(self):
        tx, events, _ = self.make()
        tx.verify_stopped = lambda: asyncio.sleep(0, result=False)
        with self.assertRaisesRegex(RuntimeError, 'stop was not verified'):
            await tx.run()
        self.assertIn('canonical off', events)
        self.assertNotIn('restore production', events)

    async def test_cancellation_runs_idempotent_containment(self):
        tx, events, _ = self.make()
        async def cancel(_):
            raise asyncio.CancelledError()
        tx.sleep = cancel
        with self.assertRaises(asyncio.CancelledError):
            await tx.run()
        first_count = events.count('canonical off')
        self.assertEqual(first_count, 1)
        self.assertTrue(await tx._contain_and_restore())
        self.assertEqual(events.count('canonical off'), first_count)

    async def test_lease_must_be_unarmed_and_healthy_before_stop(self):
        tx, events, _ = self.make()
        tx.lease.read_state = lambda: asyncio.sleep(0, result=SimpleNamespace(
            armed=True, tripped=False, boot_quarantine=False, modbus_age_s=1))
        with self.assertRaisesRegex(RuntimeError, 'healthy, unarmed'):
            await tx.run()
        self.assertNotIn('stop production', events)

    async def test_typed_adoption_must_report_success(self):
        tx, events, _ = self.make(adoption_ok=False)
        with self.assertRaisesRegex(RuntimeError, 'typed D061 adoption failed'):
            await tx.run()
        self.assertIn('stop acceptance', events)
        self.assertLess(events.index('independent OFF'), events.index('restore production'))
        self.assertEqual(tx.evidence['typed_responses']['d061_adopt_battery'],
                         {'ok': False, 'error': {'code': 'ADOPTION_REJECTED', 'detail': 'test'}})

    async def test_typed_success_responses_are_retained(self):
        tx, _, _ = self.make()
        self.assertTrue(await tx.run())
        self.assertEqual(tx.evidence['typed_responses'], {
            'd061_adopt_battery': {'ok': True, 'result': {'adopted': True}},
            'd061_verified_stop': {'ok': True, 'result': {'stopped': True, 'output': 'off'}},
        })

    async def test_typed_stop_failure_contains_before_restore(self):
        tx, events, _ = self.make(stop_ok=False)
        with self.assertRaisesRegex(RuntimeError, 'typed D061 verified stop failed'):
            await tx.run()
        self.assertEqual(tx.evidence['typed_responses']['d061_verified_stop'],
                         {'ok': False, 'error': {'code': 'STOP_REJECTED', 'detail': 'test'}})
        self.assertIn('canonical off', events)
        self.assertLess(events.index('independent OFF'), events.index('restore production'))

    async def test_acceptance_stop_failure_never_restores_production(self):
        tx, events, _ = self.make()
        async def fail_stop():
            events.append('stop acceptance failed')
            raise RuntimeError('task did not stop')
        tx.stop_acceptance = fail_stop
        with self.assertRaisesRegex(RuntimeError, 'containment is unresolved'):
            await tx.run()
        self.assertIn('canonical off', events)
        self.assertNotIn('restore production', events)

    async def test_unknown_post_off_ownership_prevents_production_restart(self):
        tx, events, _ = self.make()
        original = tx.control
        async def unknown_status(op, **kwargs):
            if op == 'status':
                return {'ok': True, 'result': {'rd_control_mode': 'unknown',
                    'output': 'off', 'output_state_code_v2': 0}}
            return await original(op, **kwargs)
        tx.control = unknown_status
        with self.assertRaisesRegex(RuntimeError, 'containment is unresolved'):
            await tx.run()
        self.assertIn('independent OFF', events)
        self.assertNotIn('restore production', events)


class TakeoverRunnerTests(unittest.IsolatedAsyncioTestCase):
    def make(self, **kwargs):
        return TakeoverTests.make(self, **kwargs)

    async def test_independent_off_requires_fresh_ha_and_native_sensor_state(self):
        from datetime import datetime, timezone
        import time
        wall = time.time()
        mono = time.monotonic()
        stamp = datetime.fromtimestamp(wall - 1, tz=timezone.utc).isoformat()
        class HA:
            async def _get(self, _entity):
                return {'state': '0.0', 'last_reported': stamp}
        class ESP:
            async def get_physical_output_report(self):
                return 0.0, {'status': 'ok', 'native_type': 'SensorState',
                    'age_s': 1.0, 'subscription_timestamp_monotonic': mono}
        args = dict(wall_time=lambda: wall, monotonic=lambda: mono)
        self.assertTrue(await independent_output_off(HA(), ESP(), 'sensor.out', **args))

        class FalseESP(ESP):
            async def get_physical_output_report(self):
                return False, {'status': 'ok', 'native_type': 'SensorState',
                    'age_s': 1.0, 'subscription_timestamp_monotonic': mono}
        self.assertFalse(await independent_output_off(HA(), FalseESP(), 'sensor.out', **args))

        class WrongTypeESP(ESP):
            async def get_physical_output_report(self):
                return 0.0, {'status': 'ok', 'native_type': 'NumberState',
                    'age_s': 1.0, 'subscription_timestamp_monotonic': mono}
        self.assertFalse(await independent_output_off(HA(), WrongTypeESP(), 'sensor.out', **args))

        class StaleESP(ESP):
            async def get_physical_output_report(self):
                return 0.0, {'status': 'ok', 'native_type': 'SensorState',
                    'age_s': 9.0, 'subscription_timestamp_monotonic': mono - 9}
        self.assertFalse(await independent_output_off(HA(), StaleESP(), 'sensor.out', **args))

        class StaleHA(HA):
            async def _get(self, _entity):
                old = datetime.fromtimestamp(wall - 9, tz=timezone.utc).isoformat()
                return {'state': '0.0', 'last_reported': old}
        self.assertFalse(await independent_output_off(StaleHA(), ESP(), 'sensor.out', **args))

        class OnHA(HA):
            async def _get(self, _entity):
                return {'state': 'on', 'last_reported': stamp}
        self.assertFalse(await independent_output_off(OnHA(), ESP(), 'sensor.out', **args))

    def test_overlay_only_adds_reviewed_acceptance_modules(self):
        from tools.acceptance_guard import pairing
        manifest=(Path(__file__).resolve().parents[1] /
                  'tools/acceptance_guard/source-manifest.json').read_bytes()
        archive_bytes=runner.make_takeover_overlay(manifest)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
            names=archive.getnames()
            allowed={'source-manifest.json','overlay-attestation.json'} | {
                'tools/acceptance_guard/'+name for name in runner.TAKEOVER_OVERLAY}
            self.assertEqual(set(names), allowed)
            self.assertEqual(len(names),len(set(names)))
            self.assertEqual(archive.extractfile('source-manifest.json').read(),manifest)
            self.assertNotIn('edge_safety_lease.py',names)
            self.assertNotIn('hass_api.py',names)
            self.assertEqual(pairing.SUPPLEMENTAL_PATHS, allowed-{
                'source-manifest.json','overlay-attestation.json'})

    def test_manifest_is_rejected_before_archive_creation_when_hash_is_wrong(self):
        with patch.object(runner, 'MANIFEST_SHA256', 'a' * 64):
            with self.assertRaisesRegex(RuntimeError, 'untrusted exact-source manifest'):
                runner.make_takeover_overlay(b'{}')

    def test_archive_stage_pairs_all_manifest_files_and_rejects_tampering(self):
        import hashlib
        import json
        import tempfile
        from tools.acceptance_guard import pairing
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / 'candidate'
            candidate.mkdir()
            expected = {}
            for index in range(875):
                name = f'canonical/{index:03}.py'
                path = candidate / name
                path.parent.mkdir(parents=True, exist_ok=True)
                content = f'canonical-source-{index}\n'.encode()
                path.write_bytes(content)
                expected[name] = hashlib.sha256(content).hexdigest()
            manifest = (json.dumps(expected, sort_keys=True, separators=(',', ':')) + '\n').encode()
            manifest_path=root/'source-manifest.json'
            manifest_path.write_bytes(manifest)
            with patch.object(pairing, 'MANIFEST_SHA256', hashlib.sha256(manifest).hexdigest()):
                self.assertEqual(pairing.verify_source(candidate,manifest_path),875)
                (candidate / 'canonical/000.py').write_text('modified')
                with self.assertRaisesRegex(RuntimeError, 'exact canonical pairing source mismatch'):
                    pairing.verify_source(candidate,manifest_path)

    def test_remote_command_uses_isolated_state_and_physical_control_opt_in(self):
        command = runner.remote_takeover_command('/tmp/stage')
        self.assertIn('RD6018_PHYSICAL_TEST_CONTROL=1', command)
        self.assertIn('/tmp/stage/state', command)
        self.assertIn('run_node104', command)
        self.assertNotIn('telegram', command.lower())

    def test_cli_failure_retains_recovery_stage_and_archives(self):
        calls = []
        stderr = io.StringIO()
        with patch.object(runner.staging, 'remote_exec', side_effect=lambda *_args, **_kwargs: calls.append('delete')):
            with contextlib.redirect_stderr(stderr):
                runner.cleanup_remote_staging(object(), '/tmp/stage',
                    ('/tmp/source.tar', '/tmp/overlay.tar.gz'), completed=False)
        self.assertEqual(calls, [])
        self.assertIn('/tmp/stage', stderr.getvalue())

    async def test_node104_runner_requires_stage_manifest_and_assembles_before_run(self):
        with __import__('tempfile').TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / 'state').mkdir()
            manifest = stage / 'source-manifest.json'
            manifest.write_text('{}')
            calls = []
            async def run(stage_arg, manifest_arg, assembled):
                calls.append(('run', stage_arg, manifest_arg, assembled))
                return True
            def assemble(source, path):
                state = Path(source) / 'state' / 'rd_control_mode_v2.json'
                self.assertEqual(json.loads(state.read_text(encoding='utf-8')),
                                 {'version': 1, 'mode': 'hands_off'})
                manager = _manager(state)
                assembled = SimpleNamespace(rd_control_mode_manager=manager)
                calls.append(('assemble', source, path, assembled))
                return assembled
            hooks = {
                'assemble': assemble,
                'run': run,
            }
            self.assertTrue(await __import__('tools.acceptance_guard.takeover', fromlist=['run_node104']).run_node104(stage, hooks=hooks))
            self.assertEqual([call[0] for call in calls], ['assemble', 'run'])
            self.assertIs(calls[0][3].rd_control_mode_manager.mode,
                          RdControlMode.HANDS_OFF)
            self.assertIs(calls[1][3].rd_control_mode_manager,
                          calls[0][3].rd_control_mode_manager)

    async def test_node104_runner_fails_closed_without_manifest(self):
        with __import__('tempfile').TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'manifest unavailable'):
                await __import__('tools.acceptance_guard.takeover', fromlist=['run_node104']).run_node104(directory, hooks={})

    async def test_release_ack_failure_contains_and_restores_only_after_off(self):
        tx, events, _ = self.make(release_ok=False)
        with self.assertRaisesRegex(RuntimeError, 'release acknowledgement'):
            await tx.run()
        self.assertIn('canonical off', events)
        self.assertIn('independent OFF', events)
        self.assertIn('lease disarm', events)
        self.assertIn('restore production', events)
        self.assertNotIn('bootstrap HANDS_OFF', events)

    async def test_adoption_failure_stops_acceptance_and_restores_after_off(self):
        tx, events, _ = self.make(adoption_ok=False)
        with self.assertRaisesRegex(RuntimeError, 'adoption failed'):
            await tx.run()
        self.assertIn('canonical off', events)
        self.assertIn('stop acceptance', events)
        self.assertLess(events.index('independent OFF'), events.index('restore production'))

    async def test_verification_failure_contains_before_restore(self):
        tx, events, _ = self.make(state_ok=False, adopted_status=True)
        tx.verify_state.last_proof = {'failed_predicates': ['fingerprint_within_tolerance']}
        with self.assertRaisesRegex(RuntimeError, 'fingerprint_within_tolerance'):
            await tx.run()
        self.assertEqual(tx.evidence['post_adoption_proof']['failed_predicates'],
                         ['fingerprint_within_tolerance'])
        self.assertNotIn('canonical off', events)
        self.assertIn(('d061_verified_stop', {}), events)
        self.assertTrue(tx.evidence['cleanup_typed_responses']['d061_verified_stop']['ok'])
        self.assertTrue(tx.ownership_safe)
        self.assertTrue(tx.restored)
        self.assertLess(events.index('independent OFF'), events.index('restore production'))

    async def test_failed_typed_cleanup_falls_back_to_immediate_fault_off(self):
        tx, events, _ = self.make(state_ok=False, adopted_status=True, stop_ok=False)
        with self.assertRaisesRegex(RuntimeError, 'setpoint proof'):
            await tx.run()
        self.assertIn(('d061_verified_stop', {}), events)
        self.assertIn('canonical off', events)
        self.assertFalse(tx.evidence['cleanup_typed_responses']['d061_verified_stop']['ok'])
        self.assertTrue(tx.output_off_proven)
        self.assertFalse(tx.restored)
        self.assertFalse(tx.ownership_safe)

    async def test_pre_adoption_failure_never_calls_typed_cleanup_stop(self):
        tx, events, _ = self.make(adoption_ok=False)
        with self.assertRaisesRegex(RuntimeError, 'adoption failed'):
            await tx.run()
        self.assertNotIn(('d061_verified_stop', {}), events)

    async def test_failed_independent_off_never_restores_production(self):
        tx, events, client = self.make()
        tx.independent_off = lambda: asyncio.sleep(0, result=False)
        client.enabled = True
        tx.rollback_armed = True
        tx.production_stopped = True
        self.assertFalse(await tx._contain_and_restore())
        self.assertNotIn('restore production', events)

    async def test_partial_acceptance_start_is_tracked_and_cleaned(self):
        tx, events, _ = self.make()
        async def partial_start():
            events.append('start acceptance partial')
            raise RuntimeError('startup failed')
        tx.start_acceptance = partial_start
        with self.assertRaisesRegex(RuntimeError, 'startup failed'):
            await tx.run()
        self.assertIn('stop acceptance', events)

    async def test_cleanup_can_retry_after_first_cleanup_failure(self):
        tx, events, _ = self.make()
        tx.rollback_armed = True
        tx.production_stopped = True
        results = iter((False, True))
        tx.independent_off = lambda: asyncio.sleep(0, result=next(results))
        self.assertFalse(await tx._contain_and_restore())
        self.assertTrue(await tx._contain_and_restore())
        self.assertEqual(events.count('restore production'), 1)

    async def test_cancellation_runs_shielded_cleanup(self):
        tx, events, _ = self.make()
        async def cancelled_sleep(_):
            raise asyncio.CancelledError()
        tx.sleep = cancelled_sleep
        with self.assertRaises(asyncio.CancelledError):
            await tx.run()
        self.assertIn('canonical off', events)
        self.assertIn('restore production', events)

    async def test_window_does_not_repeat_expensive_typed_verification(self):
        tx, events, _ = self.make()
        now = [0.0]
        tx.monotonic = lambda: now[0]
        async def sleep(seconds):
            now[0] += seconds
        tx.sleep = sleep
        calls = [0]
        async def slow_verify(_target):
            calls[0] += 1
            now[0] += 2.0
            return True
        tx.verify_state = slow_verify
        self.assertTrue(await tx.run())
        self.assertEqual(calls[0], 1)
        self.assertEqual(len(tx.evidence['live_samples']), 4)
        self.assertGreaterEqual(now[0], 21.8)
        self.assertLessEqual(now[0], 22.0)
        self.assertIn(('d061_verified_stop', {}), events)

    async def test_sleep_timeout_at_elapsed_deadline_is_successful_hold(self):
        tx, events, _ = self.make()
        clock = [0.0]
        tx.monotonic = lambda: clock[0]

        async def exact_deadline_sleep(_seconds):
            clock[0] = 20.01
            raise asyncio.TimeoutError()

        tx.sleep = exact_deadline_sleep
        self.assertTrue(await tx.run())
        self.assertIn(('d061_verified_stop', {}), events)
        self.assertIn('restore production', events)

    async def test_partial_service_stop_is_never_blindly_restarted(self):
        tx, events, _ = self.make()
        async def stop_then_fail():
            events.append('stop production')
            raise RuntimeError('stop outcome ambiguous')
        tx.stop_production = stop_then_fail
        with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
            await tx.run()
        self.assertNotIn('restore production', events)


if __name__ == '__main__':
    unittest.main()
