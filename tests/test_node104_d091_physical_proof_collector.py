from __future__ import annotations

import ast
import importlib.util
import math
from pathlib import Path
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools' / 'node104_d091_physical_proof_collector.py'
SPEC = importlib.util.spec_from_file_location('node104_d091_collector', SOURCE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def snapshot():
    now = time.time()
    ha_entity = {'last_reported': __import__('datetime').datetime.fromtimestamp(now, __import__('datetime').timezone.utc).isoformat(),
                 'attributes': {'unit_of_measurement': 'x'}}
    native_meta = {'status': 'ok', 'native_type': 'SensorState', 'age_s': 1.0,
                   'source': 'esp_native_api', 'object_id': 'output_state_code_v2'}
    edge = {}
    for key in M.EXPECTED_EDGE:
        edge[key] = {'value': 900.0 if key == 'edge_lease_ttl' else False,
                     'meta': {'status': 'ok', 'age_s': 1.0,
                              'native_type': 'SensorState' if key == 'edge_lease_ttl' else 'BinarySensorState',
                              'source': 'esp_native_api', 'object_id': M.EXPECTED_EDGE[key]}}
    return {'captured_at_epoch': time.time(), 'host_machine_id': 'machine', 'service_main_pid': 0,
            'matching_bot_process_count': 0, 'physical_device_count': 1,
            'device_info': {'project_name': M.EXPECTED_PROJECT, 'project_version': M.EXPECTED_VERSION,
                            'name': M.EXPECTED_NAME, 'model': M.EXPECTED_MODEL},
            'ha': {'output_state': 0, 'voltage': 0.0, 'current': 0.0,
                   'output_entity': ha_entity, 'voltage_entity': ha_entity, 'current_entity': ha_entity},
            'esp': {'output_state': 0, 'voltage': 0.0, 'current': 0.0,
                    'output_meta': native_meta,
                    'voltage_meta': dict(native_meta, object_id='output_voltage'),
                    'current_meta': dict(native_meta, object_id='output_current')},
            'edge': edge, 'active_session': False, 'journal_clear': True,
            'source_nonces': ('ha-unique', 'esp-unique')}


class CollectorProofTests(unittest.TestCase):
    def assert_rejected(self, mutate):
        value = snapshot()
        mutate(value)
        with self.assertRaises(M.ProofError):
            M.assemble_proof(value)

    def test_emits_exact_d090_shape_and_distinct_nonces(self):
        result = M.assemble_proof(snapshot())
        self.assertEqual(set(result), {'captured_at_epoch', 'host_machine_id', 'service_main_pid',
            'ha102_output_off', 'ha102_voltage_v', 'ha102_current_a', 'esp128_output_off',
            'esp128_voltage_v', 'esp128_current_a', 'native_sensor_state_fresh', 'edge_lease_armed',
            'edge_boot_quarantine', 'physical_node_owner_count', 'active_session', 'source_nonces'})
        self.assertEqual(len(set(result['source_nonces'])), 2)

    def test_native_state_stale_unknown_and_wrong_type_fail(self):
        self.assert_rejected(lambda s: s['esp']['output_meta'].__setitem__('age_s', 9))
        self.assert_rejected(lambda s: s['esp']['output_meta'].__setitem__('status', 'unknown'))
        self.assert_rejected(lambda s: s['esp']['output_meta'].__setitem__('native_type', 'NumberState'))

    def test_native_sensor_origin_and_object_id_required(self):
        for key in ('output_meta', 'voltage_meta', 'current_meta'):
            with self.subTest(meta=key):
                self.assert_rejected(lambda s, k=key:
                    s['esp'][k].__setitem__('source', 'ha102_rest'))
                self.assert_rejected(lambda s, k=key:
                    s['esp'][k].__setitem__('object_id', 'wrong-entity'))

    def test_ha_stale_missing_or_contradictory_never_veto_fresh_native(self):
        cases = (
            lambda s: s['ha']['output_entity'].__setitem__(
                'last_reported', '2000-01-01T00:00:00+00:00'),
            lambda s: s['ha']['voltage_entity'].pop('attributes'),
            lambda s: s.__setitem__('ha', None),
            lambda s: s['ha'].__setitem__('output_state', 1),
            lambda s: s['ha'].__setitem__('voltage', .1),
            lambda s: s['ha'].__setitem__('current', math.nan),
            lambda s: s['ha'].__setitem__('output_state', True),
        )
        for edit in cases:
            snap = snapshot()
            edit(snap)
            with self.subTest(ha=snap['ha']):
                result = M.assemble_proof(snap)
                self.assertTrue(result['esp128_output_off'])
                self.assertEqual(0, result['esp128_voltage_v'])
        snap = snapshot()
        snap['ha']['output_entity']['last_reported'] = '2000-01-01T00:00:00+00:00'
        out = M.assemble_proof(snap)
        self.assertIsNone(out['ha102_output_off'])
        self.assertIsNone(out['ha102_voltage_v'])

    def test_native_output_on_nonzero_or_invalid_vi_fails_with_healthy_ha(self):
        for name, bad in (('output_state', 1), ('voltage', .1), ('current', math.nan),
                          ('output_state', True)):
            with self.subTest(name=name, bad=bad):
                self.assert_rejected(lambda s, n=name, value=bad:
                                     s['esp'].__setitem__(n, value))

    def test_edge_authorities_lease_and_faults_fail_closed(self):
        for key in ('edge_lease_armed', 'edge_lease_tripped', 'edge_boot_quarantine',
                    'edge_autonomous_mode', 'edge_authority_conflict', 'edge_intrinsic_fault'):
            self.assert_rejected(lambda s, k=key: s['edge'][k].__setitem__('value', True))
        self.assert_rejected(lambda s: s['edge']['edge_lease_ttl'].__setitem__('value', 899))
        self.assert_rejected(lambda s: s['edge']['edge_lease_armed'].__setitem__('value', 0))

    def test_session_journal_identity_process_and_nonce_gates(self):
        self.assert_rejected(lambda s: s.__setitem__('active_session', True))
        self.assert_rejected(lambda s: s.__setitem__('journal_clear', False))
        self.assert_rejected(lambda s: s['device_info'].__setitem__('project_version', 'wrong'))
        self.assert_rejected(lambda s: s.__setitem__('physical_device_count', 0))
        self.assert_rejected(lambda s: s.__setitem__('matching_bot_process_count', 1))
        self.assert_rejected(lambda s: s.__setitem__('source_nonces', ('same', 'same')))

    def test_retired_records_are_exact_and_unknown_documents_rejected(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'charge_session.json'
            path.write_text('{"owner":"runtime.charge.persistence","schema_version":1,"state":"retired","stage":"RETIRED","retirement_kind":"operator_recovery_clearance","output_intent":"verified_off","verified_off_transaction_id":"x","session_id":"s","battery_id":null,"retired_utc":"now"}')
            self.assertFalse(M._session_state(path))
            path.write_text('{"stage":"done"}')
            with self.assertRaises(M.ProofError): M._session_state(path)

    def test_active_and_stopped_service_environment_loading_are_separate(self):
        import inspect
        source = inspect.getsource(M._load_service_environment)
        self.assertIn("/proc/{pid}/environ", source)
        self.assertIn('dotenv_values(env_path)', source)
        self.assertIn('stat.st_uid != 0', source)
        self.assertNotIn('print(', source)

    def test_deployed_native_cache_shape_and_device_id_zero_are_accepted(self):
        from types import SimpleNamespace
        entity = SimpleNamespace(object_id='safety_lease_armed', key=41, device_id=0)
        esp = SimpleNamespace(_state_cache={'safety_lease_armed': {'BinarySensorState': False}},
                              _state_types={'safety_lease_armed': 'BinarySensorState'},
                              _state_updated_at={'safety_lease_armed': time.monotonic()})
        value, meta = M._cached_native_state(esp, (entity,), 'safety_lease_armed')
        self.assertIs(value, False)
        self.assertEqual(meta['device_id'], 0)
        self.assertEqual(meta['native_type'], 'BinarySensorState')
        self.assertLessEqual(meta['age_s'], M.MAX_SOURCE_AGE_S)
        self.assertTrue(M.assemble_proof(snapshot())['native_sensor_state_fresh'])

    def test_device_info_async_api_does_not_require_device_id(self):
        import asyncio
        from types import SimpleNamespace
        async def device_info():
            return SimpleNamespace(project_name=M.EXPECTED_PROJECT,
                project_version=M.EXPECTED_VERSION, name=M.EXPECTED_NAME, model=M.EXPECTED_MODEL)
        info = asyncio.run(M._device_info(SimpleNamespace(device_info=device_info)))
        self.assertNotIn('device_id', info)
        self.assertEqual(info['model'], 'esp01_1m')

    def test_missing_or_stale_deployed_cache_rejected(self):
        from types import SimpleNamespace
        entity = SimpleNamespace(object_id='intrinsic_safety_fault', key=42, device_id=0)
        esp = SimpleNamespace(_state_cache={'intrinsic_safety_fault': {'BinarySensorState': False}},
            _state_types={'intrinsic_safety_fault': 'BinarySensorState'},
            _state_updated_at={'intrinsic_safety_fault': time.monotonic() - 9})
        _, meta = M._cached_native_state(esp, (entity,), 'intrinsic_safety_fault')
        with self.assertRaises(M.ProofError): M._fresh(meta)
        del esp._state_cache['intrinsic_safety_fault']
        with self.assertRaises(M.ProofError): M._cached_native_state(esp, (entity,), 'intrinsic_safety_fault')

    def test_measured_values_require_post_subscription_sensor_callbacks(self):
        import asyncio
        from types import SimpleNamespace

        class SensorInfo:
            def __init__(self, key, object_id): self.key, self.object_id, self.device_id = key, object_id, 0
        class NumberInfo:
            def __init__(self, key, object_id): self.key, self.object_id, self.device_id = key, object_id, 0
        class SensorState:
            def __init__(self, key, state): self.key, self.state = key, state
        class NumberState:
            def __init__(self, key, state): self.key, self.state = key, state

        inventory = (SensorInfo(1, 'output_state_code_v2'),
                     SensorInfo(2, 'output_voltage'), NumberInfo(20, 'output_voltage'),
                     SensorInfo(3, 'output_current'), NumberInfo(30, 'output_current'))
        class Client:
            def subscribe_states(self, callback):
                # Setpoint callbacks arrive for colliding object IDs; only the
                # measured SensorState callbacks may satisfy the proof.
                callback(SensorState(1, 0)); callback(SensorState(2, 0.0)); callback(SensorState(3, 0.0))
                time.sleep(.002)
                callback(NumberState(20, 13.57)); callback(NumberState(30, .10))
                return lambda: None

        esp = SimpleNamespace(client=Client(), entities=inventory,
            _entities_by_key={1: [inventory[0]], 2: [inventory[1]], 20: [inventory[2]],
                              3: [inventory[3]], 30: [inventory[4]]},
            _state_cache={}, _state_updated_at={}, _state_reported_at={}, _state_types={},
            _state_subscription_remover=None, _state_subscription_lock=__import__('asyncio').Lock())
        # Bind the same cache behavior as the transport without connecting to a node.
        def cache_callback(state):
            for entity in esp._entities_by_key.get(state.key, ()):
                oid = entity.object_id
                state_type = type(state).__name__
                esp._state_cache.setdefault(oid, {})[state_type] = state.state
                esp._state_updated_at[oid] = time.monotonic()
                esp._state_types[oid] = state_type
        esp._on_state = cache_callback
        async def ensure():
            esp._state_subscription_remover = esp.client.subscribe_states(esp._on_state)
        esp._ensure_state_subscription = ensure
        values = asyncio.run(M._fresh_measured_sensor_callbacks(esp, inventory,
            {'output_state': 'output_state_code_v2', 'voltage': 'output_voltage', 'current': 'output_current'}))
        self.assertEqual([values[k][0] for k in M.MEASURED_SENSOR_KEYS], [0, 0.0, 0.0])
        self.assertTrue(all(meta['native_type'] == 'SensorState' for _, meta in values.values()))
        self.assertEqual(esp._state_cache['output_voltage']['NumberState'], 13.57)
        self.assertEqual(esp._state_cache['output_current']['NumberState'], .10)
        self.assertLess(values['voltage'][1]['subscription_timestamp_monotonic'],
                        esp._state_updated_at['output_voltage'])
        self.assertLess(values['current'][1]['subscription_timestamp_monotonic'],
                        esp._state_updated_at['output_current'])

    def test_measured_values_reject_numberstate_only_wrong_key_and_no_subscription(self):
        import asyncio
        from types import SimpleNamespace

        class SensorInfo:
            def __init__(self, key, object_id): self.key, self.object_id, self.device_id = key, object_id, 0
        class SensorState:
            def __init__(self, key, state): self.key, self.state = key, state
        class NumberState:
            def __init__(self, key, state): self.key, self.state = key, state
        inventory = tuple(SensorInfo(k, oid) for k, oid in enumerate(
            ('output_state_code_v2', 'output_voltage', 'output_current'), 1))
        ids = {'output_state': inventory[0].object_id, 'voltage': inventory[1].object_id,
               'current': inventory[2].object_id}

        def make(callbacks):
            class Client:
                def subscribe_states(self, callback):
                    for state in callbacks: callback(state)
                    return lambda: None
            esp = SimpleNamespace(client=Client(), _state_cache={}, _state_updated_at={},
                _state_reported_at={}, _state_types={}, _state_subscription_remover=None,
                _state_subscription_lock=asyncio.Lock(), _entities_by_key={})
            esp._on_state = lambda _state: None
            async def ensure():
                esp._state_subscription_remover = esp.client.subscribe_states(esp._on_state)
            esp._ensure_state_subscription = ensure
            return esp

        old_wait = M.NATIVE_SENSOR_WAIT_S
        M.NATIVE_SENSOR_WAIT_S = .01
        try:
            for callbacks in ((NumberState(2, 13.57), NumberState(3, .10), SensorState(1, 0)),
                              (SensorState(1, 0), SensorState(2, 0), SensorState(99, 0))):
                with self.assertRaises(M.ProofError):
                    asyncio.run(M._fresh_measured_sensor_callbacks(make(callbacks), inventory, ids))
            esp = make((SensorState(1, 0), SensorState(2, 0), SensorState(3, 0)))
            esp.client.subscribe_states = None
            with self.assertRaises(M.ProofError):
                asyncio.run(M._fresh_measured_sensor_callbacks(esp, inventory, ids))
        finally:
            M.NATIVE_SENSOR_WAIT_S = old_wait

    def test_ast_guard_excludes_mutating_or_command_apis(self):
        tree = ast.parse(SOURCE.read_text())
        banned = {'disable_output', 'press_button', 'button_command', 'systemctl_stop', 'os.system', 'Popen'}
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ''
                if name in banned: found.add(name)
        self.assertFalse(found, found)


if __name__ == '__main__':
    unittest.main()
