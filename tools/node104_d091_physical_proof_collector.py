#!/usr/bin/env python3
"""Read-only node104 D090 physical OFF proof collector.

This module has no actuator, service control, or filesystem mutation path. The
pure snapshot assembler is intentionally separate from the live I/O adapter.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from typing import Any

ROOT = Path('/opt/services/rd6018-bot')
APP = ROOT / 'app'
SERVICE = 'rd6018-bot.service'
EXPECTED_PROJECT = 'timspb.rd6018-pb-recovery-v2'
EXPECTED_VERSION = os.environ.get('D090_EXPECTED_ESP_VERSION', '2.2-autonomous-authority')
EXPECTED_NAME = 'rd6018-controller'
EXPECTED_MODEL = 'esp01_1m'
EXPECTED_ESP_HOST = '192.168.1.28'
MAX_SOURCE_AGE_S = 8.0
NATIVE_SENSOR_WAIT_S = 10.0
MEASURED_SENSOR_KEYS = ('output_state', 'voltage', 'current')
EXPECTED_EDGE = {
    'edge_lease_armed': 'safety_lease_armed',
    'edge_lease_tripped': 'safety_lease_tripped',
    'edge_boot_quarantine': 'safety_boot_quarantine',
    'edge_lease_ttl': 'safety_lease_ttl',
    'edge_autonomous_mode': 'safety_autonomous_mode',
    'edge_authority_conflict': 'safety_authority_conflict',
    'edge_intrinsic_fault': 'intrinsic_safety_fault',
}


class ProofError(RuntimeError):
    pass


def _number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ProofError('numeric evidence is missing, boolean, or non-finite')
    return float(value)


def _ha_number(value: Any) -> float:
    # HA REST exposes sensor register values as numeric strings. Unlike an
    # HA switch, the configured R18 sensor can be parsed strictly as a number.
    # Never normalize 'off', 'unknown', bool, NaN or Infinity to physical OFF.
    if type(value) is str:
        if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', value):
            raise ProofError('HA numeric sensor is not a strict number')
        value = float(value)
    return _number(value)


def _fresh(meta: dict[str, Any], *, native: bool = False) -> None:
    if type(meta) is not dict or meta.get('status') != 'ok':
        raise ProofError('source status is not ok')
    age = meta.get('age_s')
    if type(age) not in (int, float) or not math.isfinite(age) or age < 0 or age > MAX_SOURCE_AGE_S:
        raise ProofError('source report is stale or has invalid age')
    if native and meta.get('native_type') != 'SensorState':
        raise ProofError('native state is not a SensorState callback')


def _ha_freshness(entity: dict[str, Any], now_epoch: float) -> None:
    attrs = entity.get('attributes')
    reported = entity.get('last_reported')
    if not isinstance(attrs, dict) or not isinstance(reported, str):
        raise ProofError('HA source last_reported/attributes missing')
    # HA metadata is requested explicitly by the REST state response.
    try:
        from datetime import datetime
        stamp = datetime.fromisoformat(reported.replace('Z', '+00:00')).timestamp()
    except (ValueError, OverflowError):
        raise ProofError('HA last_reported timestamp invalid')
    if not math.isfinite(stamp) or not 0 <= now_epoch - stamp <= MAX_SOURCE_AGE_S:
        raise ProofError('HA last_reported source is stale')


def _bool(value: Any) -> bool:
    if type(value) is not bool:
        raise ProofError('edge state must be a strict boolean')
    return value


def _session_state(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_symlink() or not path.is_file():
        raise ProofError('session document is not a regular file')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ProofError('session document is unreadable')
    if type(data) is not dict:
        raise ProofError('session document schema is unknown')
    # Current terminal documents remain on disk as retired records.
    if (data.get('owner') == 'runtime.charge.persistence' and data.get('schema_version') == 1
            and data.get('state') == 'retired' and data.get('stage') == 'RETIRED'
            and data.get('retirement_kind') == 'operator_recovery_clearance'
            and data.get('output_intent') == 'verified_off'
            and type(data.get('verified_off_transaction_id')) is str
            and type(data.get('session_id')) is str and 'battery_id' in data
            and type(data.get('retired_utc')) is str):
        return False
    raise ProofError('session document may represent an active charge session')


def _journal_state(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink() or not path.is_file():
        raise ProofError('quarantine journal is not a regular file')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ProofError('quarantine journal is unreadable')
    if (type(data) is dict and set(data) == {'owner', 'schema_version', 'state', 'quarantined', 'retirement'}
            and data.get('owner') == 'runtime.charge.recovery_quarantine_journal'
            and data.get('schema_version') == 2 and data.get('state') == 'retired'
            and data.get('quarantined') is False and type(data.get('retirement')) is dict):
        retirement = data['retirement']
        keys = {'operator_id', 'session_id', 'confirmed_off_evidence', 'retired_utc',
                'incident_id', 'incident_reason', 'battery_id'}
        if (set(retirement) == keys
                and all(type(retirement.get(key)) is str and retirement[key].strip()
                        for key in ('operator_id', 'session_id', 'confirmed_off_evidence',
                                    'retired_utc', 'incident_id', 'incident_reason'))
                and (retirement['battery_id'] is None or
                     (type(retirement['battery_id']) is str and retirement['battery_id'].strip()))):
            return
    raise ProofError('quarantine journal is active or has unknown schema')


def assemble_proof(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Validate independent fake/live snapshots and return exact D090 JSON schema."""
    if type(snapshot) is not dict:
        raise ProofError('snapshot must be an object')
    now = snapshot.get('captured_at_epoch')
    pid = snapshot.get('service_main_pid')
    machine = snapshot.get('host_machine_id')
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ProofError('capture timestamp invalid')
    if type(pid) is not int or pid < 0 or type(machine) is not str or not machine:
        raise ProofError('host/service identity invalid')
    if type(snapshot.get('physical_device_count')) is not int or snapshot['physical_device_count'] != 1:
        raise ProofError('exactly one matching physical ESPHome device identity is required')
    if type(snapshot.get('matching_bot_process_count')) is not int or snapshot['matching_bot_process_count'] != (1 if pid else 0):
        raise ProofError('service MainPID and matching bot process count disagree')
    info = snapshot.get('device_info')
    wanted = {'project_name': EXPECTED_PROJECT, 'project_version': EXPECTED_VERSION,
              'name': EXPECTED_NAME, 'model': EXPECTED_MODEL}
    if type(info) is not dict or any(info.get(key) != value for key, value in wanted.items()):
        raise ProofError('ESPHome device identity/project does not match reviewed node')

    ha, esp = snapshot.get('ha'), snapshot.get('esp')
    if type(ha) is not dict or type(esp) is not dict:
        raise ProofError('independent HA and native ESP snapshots required')
    for source_name, source in (('HA102', ha), ('ESP128', esp)):
        if source.get('output_state') != 0 or type(source.get('output_state')) is bool:
            raise ProofError(f'{source_name} physical R18 is not strict numeric OFF')
        voltage, current = _number(source.get('voltage')), _number(source.get('current'))
        if abs(voltage) > .05 or abs(current) > .05:
            raise ProofError(f'{source_name} physical V/I exceeds OFF tolerance: V={voltage:.4f} I={current:.4f}')
    _ha_freshness(ha.get('output_entity', {}), now)
    for key in ('voltage_entity', 'current_entity'):
        _ha_freshness(ha.get(key, {}), now)
    native = esp.get('output_meta')
    _fresh(native, native=True)
    if type(native.get('age_s')) not in (int, float) or native['age_s'] > MAX_SOURCE_AGE_S:
        raise ProofError('native R18 callback is stale')
    for key in ('voltage_meta', 'current_meta'):
        _fresh(esp.get(key, {}), native=True)

    edge = snapshot.get('edge')
    if type(edge) is not dict:
        raise ProofError('edge containment snapshot missing')
    for key in EXPECTED_EDGE:
        record = edge.get(key)
        if type(record) is not dict:
            raise ProofError('edge state missing: ' + key)
        _fresh(record.get('meta', {}))
        expected_type = 'SensorState' if key == 'edge_lease_ttl' else 'BinarySensorState'
        if record['meta'].get('native_type') != expected_type or record['meta'].get('source') != 'esp_native_api':
            raise ProofError('edge evidence is not the expected native callback type: ' + key)
        if record['meta'].get('object_id') != EXPECTED_EDGE[key]:
            raise ProofError('edge evidence object identity mismatch: ' + key)
        if key == 'edge_lease_ttl':
            if abs(_number(record.get('value')) - 900.0) > .001:
                raise ProofError('edge lease TTL is not 900 seconds')
        elif _bool(record.get('value')):
            raise ProofError('edge containment/authority/fault flag is asserted: ' + key)
    if snapshot.get('active_session') is not False:
        raise ProofError('active or uncertain session document')
    if snapshot.get('journal_clear') is not True:
        raise ProofError('quarantine journal is active or uncertain')
    nonces = snapshot.get('source_nonces')
    if type(nonces) is not tuple or len(nonces) != 2 or any(type(n) is not str or not n for n in nonces) or len(set(nonces)) != 2:
        raise ProofError('independent source read identifiers missing/reused')
    return {
        'captured_at_epoch': float(now), 'host_machine_id': machine, 'service_main_pid': pid,
        'ha102_output_off': True, 'ha102_voltage_v': float(ha['voltage']), 'ha102_current_a': float(ha['current']),
        'esp128_output_off': True, 'esp128_voltage_v': float(esp['voltage']), 'esp128_current_a': float(esp['current']),
        'native_sensor_state_fresh': True, 'edge_lease_armed': False, 'edge_boot_quarantine': False,
        'physical_node_owner_count': 1, 'active_session': False, 'source_nonces': list(nonces),
    }


def _service_identity() -> tuple[int, int]:
    pid_text = subprocess.check_output(['systemctl', 'show', SERVICE, '-p', 'MainPID', '--value'], text=True, timeout=4).strip()
    if not re.fullmatch(r'0|[1-9][0-9]*', pid_text):
        raise ProofError('systemd MainPID response invalid')
    pid = int(pid_text)
    processes: list[int] = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = proc.joinpath('cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if any(item.endswith(b'/app/bot.py') for item in argv if item):
            processes.append(int(proc.name))
    if processes != ([pid] if pid else []):
        raise ProofError('matching bot processes do not agree exactly with systemd MainPID')
    return pid, len(processes)


def _load_service_environment(pid: int) -> None:
    if pid:
        raw = Path(f'/proc/{pid}/environ').read_bytes()
        for item in raw.split(b'\0'):
            if b'=' in item:
                key, value = item.split(b'=', 1)
                try:
                    name = key.decode()
                    if name in {'HA_TOKEN', 'ESPHOME_API_KEY', 'HA_URL', 'HA_LOCAL_URL', 'ESPHOME_API_HOST', 'ESPHOME_API_PORT', 'RD6018_CONNECTOR', 'RD6018_CONFIG_DIR'}:
                        os.environ[name] = value.decode()
                except UnicodeError:
                    continue
    else:
        env_path = ROOT / '.env'
        try:
            stat = env_path.lstat()
        except OSError as exc:
            raise ProofError('stopped service environment file is unavailable') from exc
        if env_path.is_symlink() or not env_path.is_file() or stat.st_uid != 0:
            raise ProofError('stopped service environment must be a root-owned regular file')
        try:
            from dotenv import dotenv_values
            values = dotenv_values(env_path)
        except Exception as exc:
            raise ProofError('cannot load stopped service environment') from exc
        for name in ('HA_TOKEN', 'ESPHOME_API_KEY', 'HA_URL', 'HA_LOCAL_URL', 'ESPHOME_API_HOST', 'ESPHOME_API_PORT', 'RD6018_CONNECTOR', 'RD6018_CONFIG_DIR'):
            if values.get(name):
                os.environ[name] = str(values[name])


async def _device_info(client: Any) -> dict[str, Any]:
    method = getattr(client, 'device_info', None)
    if not callable(method):
        raise ProofError('ESPHome API does not expose device_info identity')
    result = await asyncio.wait_for(method(), timeout=5)
    if type(result) is not dict:
        converter = getattr(result, 'to_dict', None)
        if callable(converter):
            result = converter()
        else:
            result = {key: getattr(result, key, None) for key in
                      ('project_name', 'project_version', 'name', 'model')}
    fields = ('project_name', 'project_version', 'name', 'model')
    info = {key: result.get(key) for key in fields}
    return info


def _cached_native_state(esp: Any, inventory: tuple[Any, ...], object_id: str) -> tuple[Any, dict[str, Any]]:
    """Read the old transport's callback cache without a newer private method."""
    entity = next((item for item in inventory if str(getattr(item, 'object_id', '')) == object_id), None)
    if entity is None or getattr(entity, 'device_id', None) is None:
        raise ProofError('required native entity identity is absent: ' + object_id)
    cache = getattr(esp, '_state_cache', {})
    updated_at = getattr(esp, '_state_updated_at', {}).get(object_id)
    state_type = getattr(esp, '_state_types', {}).get(object_id)
    values = cache.get(object_id)
    if type(values) is not dict or state_type not in values:
        raise ProofError('required native callback is absent: ' + object_id)
    age = None if updated_at is None else max(0.0, time.monotonic() - updated_at)
    return values[state_type], {'source': 'esp_native_api', 'object_id': object_id,
        'status': 'ok', 'native_type': state_type, 'entity_type': type(entity).__name__,
        'age_s': age, 'subscription_timestamp_monotonic': updated_at,
        'key': int(entity.key), 'device_id': int(entity.device_id)}


async def _fresh_measured_sensor_callbacks(esp: Any, inventory: tuple[Any, ...],
                                           object_ids: dict[str, str]) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Capture new, typed measurement callbacks from the passive API subscription."""
    if not callable(getattr(getattr(esp, 'client', None), 'subscribe_states', None)):
        raise ProofError('native state subscription is unavailable')
    selected: dict[int, tuple[str, Any]] = {}
    for name in MEASURED_SENSOR_KEYS:
        object_id = object_ids.get(name)
        entity = next((item for item in inventory if str(getattr(item, 'object_id', '')) == object_id), None)
        if entity is None or type(entity).__name__ != 'SensorInfo':
            raise ProofError('measured native entity is absent or not SensorInfo: ' + str(object_id))
        key = int(entity.key)
        if key in selected:
            raise ProofError('measured native SensorInfo keys are not unique')
        selected[key] = (name, object_id, entity)

    loop = asyncio.get_running_loop()
    ready = asyncio.Event()
    captured: dict[str, tuple[Any, dict[str, Any]]] = {}
    original = getattr(esp, '_on_state', None)
    if not callable(original):
        raise ProofError('native state callback is unavailable')

    def observe(state: Any) -> None:
        original(state)
        if type(state).__name__ != 'SensorState':
            return
        match = selected.get(getattr(state, 'key', None))
        if match is None:
            return
        name, object_id, entity = match
        timestamp = time.monotonic()
        meta = {'source': 'esp_native_api', 'object_id': object_id, 'status': 'ok',
                'native_type': 'SensorState', 'entity_type': 'SensorInfo',
                'age_s': max(0.0, time.monotonic() - timestamp),
                'subscription_timestamp_monotonic': timestamp,
                'key': int(entity.key), 'device_id': int(entity.device_id)}
        captured[name] = (getattr(state, 'state', None), meta)
        if all(name in captured for name in MEASURED_SENSOR_KEYS):
            loop.call_soon_threadsafe(ready.set)

    # A fresh transport has not subscribed yet. Install the observer before
    # `_ensure_state_subscription` so only callbacks from this collection count.
    esp._on_state = observe
    try:
        await asyncio.wait_for(esp._ensure_state_subscription(), timeout=5)
        await asyncio.wait_for(ready.wait(), timeout=NATIVE_SENSOR_WAIT_S)
    except asyncio.TimeoutError as exc:
        raise ProofError('fresh typed SensorState measurement callbacks missing within 10 seconds') from exc
    finally:
        esp._on_state = original
    result = {}
    for name in MEASURED_SENSOR_KEYS:
        value, meta = captured[name]
        meta['age_s'] = max(0.0, time.monotonic() - meta['subscription_timestamp_monotonic'])
        _fresh(meta, native=True)
        _number(value)
        result[name] = (value, meta)
    return result


async def collect_live() -> dict[str, Any]:
    """Connect to existing configured read transports and collect one snapshot."""
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    from runtime.config import load_config
    from runtime.physical.transports.ha102 import HA102Transport
    from runtime.physical.transports.esp128 import ESPHomeTransport
    pid, proc_count = _service_identity()
    _load_service_environment(pid)
    config = load_config(ROOT / 'app' / 'config')
    if config.default_connector != 'esp_direct':
        raise ProofError('configured connector is not esp_direct')
    ha_config, esp_config = config.transports.get('ha102'), config.transports.get('esp128')
    if ha_config is None or esp_config is None:
        raise ProofError('independent HA102 and ESP128 transports are not configured')
    if esp_config.connection.host and esp_config.connection.host != EXPECTED_ESP_HOST:
        raise ProofError('configured native ESP host does not match reviewed node identity')
    ha, esp = HA102Transport(ha_config, config.rd), ESPHomeTransport(esp_config, config.rd)
    try:
        # Native discover/subscription is strictly observational.
        await asyncio.wait_for(esp.discover(), timeout=8)
        info = await _device_info(esp.client)
        # The deployed 8b75cca API reports no device_id in device_info. Native
        # inventory carries device_id=0 on every entity; use that inventory as
        # the physical identity and require it to be unique and complete.
        inventory = tuple(esp.entities)
        if not inventory or any(getattr(entity, 'device_id', None) is None for entity in inventory):
            raise ProofError('native entity inventory has missing physical device identity')
        physical_ids = {int(entity.device_id) for entity in inventory}
        if len(physical_ids) != 1:
            raise ProofError('native entity inventory has unknown/competing device identity')
        # The deployed 8b75cca transport's get_entity_state cannot resolve
        # certain configured object IDs, even though the native subscription
        # receives them. Read the original typed callback cache directly,
        # never infer OFF from a missing state or fall back to HA.
        native = await _fresh_measured_sensor_callbacks(esp, inventory, esp_config.entities)
        esp_snapshot = {'output_state': _number(native['output_state'][0]),
                        'voltage': _number(native['voltage'][0]), 'current': _number(native['current'][0]),
                        'output_meta': native['output_state'][1], 'voltage_meta': native['voltage'][1],
                        'current_meta': native['current'][1]}
        edge = {}
        # This is a subscription-cache-only read for older deployed API clients.
        # No entity command path is used; values must originate in native callbacks.
        await asyncio.sleep(.5)
        for key, object_id in EXPECTED_EDGE.items():
            value, meta = _cached_native_state(esp, inventory, object_id)
            edge[key] = {'value': value, 'meta': meta}
        # HA REST reads occur after the native wait so last_reported remains
        # current when the independent source snapshot is assembled.
        ha_entities = {}
        for key in MEASURED_SENSOR_KEYS:
            entity_id = ha_config.entities.get(key)
            if not entity_id:
                raise ProofError('required HA read-only entity mapping missing')
            ha_entities[key] = await asyncio.wait_for(ha._get(entity_id), timeout=5)
        ha_snapshot = {
            'output_state': _ha_number(ha_entities['output_state'].get('state')),
            'voltage': _ha_number(ha_entities['voltage'].get('state')),
            'current': _ha_number(ha_entities['current'].get('state')),
            'output_entity': ha_entities['output_state'], 'voltage_entity': ha_entities['voltage'],
            'current_entity': ha_entities['current'],
        }
        session_path = Path(os.getenv('RD6018_STATE_DIR', str(ROOT / 'state'))) / 'charge_session.json'
        journal_path = session_path.parent / 'session_recovery_quarantine.json'
        snapshot = {
            'captured_at_epoch': time.time(), 'host_machine_id': Path('/etc/machine-id').read_text().strip(),
            'service_main_pid': pid, 'matching_bot_process_count': proc_count,
            'physical_device_count': len(physical_ids), 'device_info': info,
            'ha': ha_snapshot, 'esp': esp_snapshot, 'edge': edge,
            'active_session': _session_state(session_path), 'journal_clear': True,
            'source_nonces': (uuid.uuid4().hex, uuid.uuid4().hex),
        }
        _journal_state(journal_path)
        return snapshot
    finally:
        await asyncio.gather(ha.close(), esp.close(), return_exceptions=True)


def main() -> int:
    try:
        result = assemble_proof(asyncio.run(asyncio.wait_for(collect_live(), timeout=35)))
        print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
        return 0
    except Exception as exc:
        print(f'node104 D091 proof collection failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
