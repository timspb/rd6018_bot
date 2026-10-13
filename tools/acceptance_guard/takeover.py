"""Supervised D061 positive-takeover smoke transaction.

This module coordinates injected canonical APIs. It contains no HA/ESP actuator
transport and is deliberately hardware inert until a caller supplies the
canonical client, edge lease, pairing lifecycle and typed control client.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import math
import time
from datetime import datetime, timezone


TARGET = {
    "voltage_v": 13.57,
    "current_a": 0.10,
    "ovp_v": 14.07,
    "ocp_a": 0.20,
}
BATTERY_NAME = "Leoch_72Ah"


def fingerprint_matches(fingerprint, target, *, tolerance=0.02):
    """Compare a complete fingerprint using finite numeric readback tolerance."""
    keys = (('set_voltage_v', 'voltage_v'), ('set_current_a', 'current_a'),
            ('ovp_v', 'ovp_v'), ('ocp_a', 'ocp_a'))
    if not isinstance(fingerprint, dict) or not isinstance(target, dict):
        return False
    for actual_key, target_key in keys:
        actual = fingerprint.get(actual_key)
        expected = target.get(target_key)
        if isinstance(actual, bool) or isinstance(expected, bool):
            return False
        try:
            actual, expected = float(actual), float(expected)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(actual) or not math.isfinite(expected) or abs(actual - expected) >= tolerance:
            return False
    return True


def seed_isolated_hands_off_state(state_dir):
    """Create and validate the isolated ownership state before bot assembly."""
    state_dir = Path(state_dir)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_path = state_dir / 'rd_control_mode_v2.json'
    document = {'version': 1, 'mode': 'hands_off'}
    encoded = json.dumps(document, sort_keys=True) + '\n'
    state_path.write_text(encoded, encoding='utf-8')
    state_path.chmod(0o600)
    # Validate the exact versioned state we expect the canonical manager to load.
    loaded = json.loads(state_path.read_text(encoding='utf-8'))
    if loaded != document or state_path.stat().st_mode & 0o077:
        raise RuntimeError('isolated HANDS_OFF ownership state failed validation')
    return state_path


def require_hands_off_manager(manager):
    mode = getattr(manager, 'mode', None)
    if (manager is None or getattr(mode, 'value', None) != 'hands_off'
            or getattr(manager, 'persistence_ok', False) is not True):
        raise RuntimeError('assembled canonical RD control-mode manager is not HANDS_OFF')
    return manager


def select_leoch_battery(conn, name):
    """Resolve exactly one persisted Ca/Ca battery without changing the DB.

    The canonical registry enum is 'ca_ca'; the human display name is Ca/Ca.
    """
    rows = conn.execute(
        "SELECT battery_id FROM batteries WHERE manufacturer=? "
        "AND chemistry=? AND nominal_capacity_ah=? "
        "AND (model=? OR battery_id=?)",
        ('Leoch', 'ca_ca', 72, name, name)).fetchall()
    if len(rows) != 1:
        raise RuntimeError('expected exactly one saved Leoch Ca/Ca 72Ah battery record')
    return str(rows[0][0])


async def independent_output_off(ha, esp, ha_entity, *, wall_time=time.time,
                                 monotonic=time.monotonic,
                                 voltage_entity=None, current_entity=None):
    """Require fresh HA and native SensorState reports of physical Output OFF."""
    if not ha_entity:
        return False
    try:
        report = await ha._get(ha_entity)
        stamp = report.get('last_reported') or report.get('last_updated')
        reported = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if reported.tzinfo is None:
            reported = reported.replace(tzinfo=timezone.utc)
        age = wall_time() - reported.timestamp()
        if not (math.isfinite(age) and 0 <= age <= 8):
            return False
        # HA reports this entity as a numeric SensorState ('0.0'), not a
        # switch's literal 'off'. Do not treat unknown/unavailable as OFF.
        ha_state = report.get('state')
        if ha_entity.startswith('sensor.'):
            try:
                ha_off = (not isinstance(ha_state, bool)
                    and math.isfinite(float(ha_state)) and float(ha_state) == 0.0)
            except (ValueError, TypeError, OverflowError):
                return False
        elif ha_entity.startswith('switch.'):
            ha_off = isinstance(ha_state, str) and ha_state.strip().lower() == 'off'
        else:
            return False
        if not ha_off:
            return False
        for entity_id in (voltage_entity, current_entity):
            if entity_id is None:
                continue
            measurement = await ha._get(entity_id)
            stamp = measurement.get('last_reported') or measurement.get('last_updated')
            reported = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if reported.tzinfo is None:
                reported = reported.replace(tzinfo=timezone.utc)
            age = wall_time() - reported.timestamp()
            raw = measurement.get('state')
            if (not math.isfinite(age) or not 0 <= age <= 8 or isinstance(raw, bool)
                    or not math.isfinite(float(raw)) or abs(float(raw)) > 0.02):
                return False
        value, meta = await esp.get_physical_output_report()
        updated = meta.get('subscription_timestamp_monotonic')
        native_age = meta.get('age_s')
        if (meta.get('status') != 'ok' or meta.get('native_type') != 'SensorState'
                or isinstance(updated, bool) or not isinstance(updated, (int, float))
                or not math.isfinite(updated)
                or not 0 <= monotonic() - updated <= 8
                or isinstance(native_age, bool) or not isinstance(native_age, (int, float))
                or not math.isfinite(native_age) or not 0 <= native_age <= 8):
            return False
        return (not isinstance(value, bool) and math.isfinite(float(value))
                and float(value) == 0.0)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False


class D061TakeoverSmoke:
    @staticmethod
    def _temperature_ok(live, *, pre_enable=False):
        meta = live.get('_meta') or {}
        for key in ('temp_int', 'temp_ext'):
            row = meta.get(key) or {}
            age = row.get('age_s')
            value = live.get(key)
            if (str(row.get('status', '')).lower() != 'ok'
                    or isinstance(age, bool) or not isinstance(age, (int, float))
                    or not math.isfinite(age) or not 0 <= age <= 8
                    or isinstance(value, bool)):
                return False
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError):
                return False
            if not math.isfinite(value) or not -20 <= value <= 100:
                return False
            # Canonical intrinsic local PSU/block cutoff is 55 C. 38 C was a
            # prior-run observation, not a safety threshold. The external
            # probe is battery temperature and has its own application rules.
            if key == 'temp_int' and value >= 55.0:
                return False
        return True

    """Execute the positive takeover with injectable canonical boundaries."""

    def __init__(self, *, client, lease, stop_production, verify_stopped,
                 bootstrap_hands_off, start_acceptance, control,
                 locate_battery, verify_state, stop_acceptance,
                 independent_off, restore_production, sleep=asyncio.sleep,
                 duration_s=20, monotonic=None, recover_off_pending=None):
        self.client = client
        self.lease = lease
        self.stop_production = stop_production
        self.verify_stopped = verify_stopped
        self.bootstrap_hands_off = bootstrap_hands_off
        self.start_acceptance = start_acceptance
        self.control = control
        self.locate_battery = locate_battery
        self.verify_state = verify_state
        self.stop_acceptance = stop_acceptance
        self.independent_off = independent_off
        self.restore_production = restore_production
        self.recover_off_pending = recover_off_pending
        self.sleep = sleep
        self.monotonic = monotonic
        self.duration_s = float(duration_s)
        self.production_stopped = False
        self.acceptance_started = False
        self.restored = False
        self.released = False
        self.rollback_armed = False
        self.lease_attempted = False
        self._cleanup_lock = asyncio.Lock()
        self._cleanup_complete = False
        self.output_off_proven = False
        self.lease_disarmed = False
        self.ownership_safe = False
        self.acceptance_stopped = False
        self.evidence = {'monotonic_unit': 'seconds from process monotonic clock',
                         'events': [], 'live_samples': [], 'typed_responses': {}}

    def _record(self, event, **fields):
        clock = self.monotonic or time.monotonic
        self.evidence['events'].append({'event': event, 'monotonic_s': clock(), **fields})

    @staticmethod
    def _source_fresh(row):
        age = (row or {}).get('age_s')
        return (str((row or {}).get('status', '')).lower() == 'ok'
                and not isinstance(age, bool) and isinstance(age, (int, float))
                and math.isfinite(age) and 0 <= age <= 8)

    async def _fresh_off(self):
        live = await self.client.get_all_live()
        meta = live.get('_meta') or {}
        def numeric(key):
            value = live.get(key)
            if isinstance(value, bool):
                return None
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError):
                return None
            return value if math.isfinite(value) else None
        required = ('switch', 'output_state_code_v2', 'voltage', 'current',
                    'protection_code', 'set_voltage_readback_v2',
                    'set_current_readback_v2', 'ovp_readback_v2',
                    'ocp_readback_v2', 'temp_int', 'temp_ext')
        for key in required:
            if not self._source_fresh(meta.get(key)):
                raise RuntimeError('fresh Output, protection, setpoint, and temperature preflight unavailable: ' + key)
        if str(live.get('switch', '')).lower() != 'off' or str(
                live.get('output_state_code_v2', '')).lower() not in ('0', '0.0', 'off'):
            raise RuntimeError('preflight requires positively confirmed Output OFF')
        for key in ('voltage', 'current'):
            value = numeric(key)
            if value is None or abs(value) > 0.02:
                raise RuntimeError('preflight requires Output voltage/current at 0')
        protection = numeric('protection_code')
        if protection is None or protection != 0.0:
            raise RuntimeError('preflight requires raw protection NORMAL')
        expected = {
            'set_voltage_readback_v2': TARGET['voltage_v'],
            'set_current_readback_v2': TARGET['current_a'],
            'ovp_readback_v2': TARGET['ovp_v'],
            'ocp_readback_v2': TARGET['ocp_a'],
        }
        for key, target in expected.items():
            value = numeric(key)
            if value is None or abs(value - target) >= 0.02:
                raise RuntimeError('preflight setpoint fingerprint mismatch: ' + key)
        if not self._temperature_ok(live, pre_enable=True):
            raise RuntimeError('fresh safe PSU/block and battery temperature evidence required')
        self.evidence['preflight'] = {
            'output_state': live.get('output_state_code_v2'),
            'output_voltage_v': live.get('voltage'),
            'output_current_a': live.get('current'),
            'set_voltage_v': numeric('set_voltage_readback_v2'),
            'set_current_a': numeric('set_current_readback_v2'),
            'ovp_v': numeric('ovp_readback_v2'),
            'ocp_a': numeric('ocp_readback_v2'),
            'raw_protection_code': numeric('protection_code'),
            'temp_int_psu_c': live.get('temp_int'),
            'temp_ext_battery_c': live.get('temp_ext'),
            'source_ages_s': {key: meta[key].get('age_s') for key in required},
        }

    async def _prove_on(self):
        live = await self.client.get_all_live()
        meta = live.get('_meta') or {}
        if not all(self._source_fresh(meta.get(key))
                   for key in ('switch', 'output_state_code_v2')):
            raise RuntimeError('fresh dual-source Output ON readback unavailable')
        if str(live.get('switch', '')).lower() != 'on' or str(
                live.get('output_state_code_v2', '')).lower() not in ('1', '1.0', 'on'):
            raise RuntimeError('canonical safe enable did not positively verify Output ON')
        if not self._temperature_ok(live):
            raise RuntimeError('PSU/block or battery temperature evidence unsafe after enable')
        clock = self.monotonic or time.monotonic
        self.evidence['physical_on'] = {
            'monotonic_s': clock(),
            'output_state': live.get('output_state_code_v2'),
            'output_voltage_v': live.get('voltage'),
            'output_current_a': live.get('current'),
            'set_voltage_v': live.get('set_voltage_readback_v2'),
            'set_current_a': live.get('set_current_readback_v2'),
            'ovp_v': live.get('ovp_readback_v2'),
            'ocp_a': live.get('ocp_readback_v2'),
            'raw_protection_code': live.get('protection_code'),
            'temp_int_psu_c': live.get('temp_int'),
            'temp_ext_battery_c': live.get('temp_ext'),
        }

    async def _wait_for_on_dwell(self):
        guard = getattr(self.client, 'guard', None)
        if guard is None:
            raise RuntimeError('canonical source-report dwell guard is unavailable')
        clock = self.monotonic or asyncio.get_running_loop().time
        deadline = clock() + 45.0
        while True:
            live = await self.client.get_all_live()
            meta = live.get('_meta') or {}
            if any(not self._source_fresh(meta.get(key))
                   for key in ('switch', 'output_state_code_v2')):
                raise RuntimeError('fresh dual-source OFF reports unavailable before enable')
            if (str(live.get('switch', '')).strip().lower() != 'off'
                    or str(live.get('output_state_code_v2', '')).strip().lower() not in ('0', '0.0', 'off')):
                raise RuntimeError('Output OFF evidence lost before enable')
            if not self._temperature_ok(live, pre_enable=True):
                raise RuntimeError('fresh safe PSU/block and battery temperature evidence required')
            try:
                guard.require_transition(True)
                return
            except Exception as exc:
                if exc.__class__.__name__ != 'Blocked':
                    raise
            if clock() >= deadline:
                raise RuntimeError('12 second fresh OFF source-report dwell was not established')
            await self.sleep(0.5)

    async def _disarm_verified(self):
        if await self.lease.disarm() is not True:
            return False
        state = await self.lease.read_state()
        modbus_age = getattr(state, 'modbus_age_s', None)
        remaining = getattr(state, 'remaining_s', None)
        slack = float(getattr(getattr(self.lease, 'config', None),
                              'ack_remaining_slack_s', 15.0))
        valid = (getattr(state, 'armed', None) is False
                and getattr(state, 'tripped', None) is False
                and getattr(state, 'boot_quarantine', None) is False
                and not isinstance(modbus_age, bool)
                and isinstance(modbus_age, (int, float))
                and math.isfinite(modbus_age) and 0 <= modbus_age <= 20
                and not isinstance(remaining, bool)
                and isinstance(remaining, (int, float))
                and math.isfinite(remaining) and 0 <= remaining <= slack)
        self.evidence['lease_disarmed'] = {
            'generation': getattr(state, 'generation', None),
            'remaining_s': remaining,
            'armed': getattr(state, 'armed', None),
            'tripped': getattr(state, 'tripped', None),
            'boot_quarantine': getattr(state, 'boot_quarantine', None),
            'modbus_age_s': modbus_age,
            'acknowledged': valid,
        }
        self._record('lease-disarm-readback', generation=getattr(state, 'generation', None),
                     remaining_s=remaining, acknowledged=valid)
        return valid

    async def _ownership_safe_after_off(self):
        result = await self.control('status')
        if result.get('ok') is not True:
            return False
        status = result.get('result')
        if not isinstance(status, dict):
            return False
        mode = status.get('rd_control_mode')
        adoption = status.get('adoption_state')
        manual = status.get('manual_state')
        return (mode in ('hands_off', 'pb_managed')
                and str(status.get('output', '')).lower() == 'off'
                and str(status.get('output_state_code_v2', '')).strip() in ('0', '0.0')
                and (mode == 'hands_off' or adoption in ('failed', 'completed', 'interrupted', 'idle'))
                and (mode == 'hands_off' or manual in ('stopped', 'failed', 'idle')))

    async def _contain_and_restore(self):
        # A completed D061 adoption is retired through the typed lifecycle API
        # when possible. Any unavailable or ambiguous stop falls through to
        # immediate fault OFF; containment must never depend on typed cleanup.
        async with self._cleanup_lock:
            if self._cleanup_complete:
                return True
            typed_stopped = False
            if self.acceptance_started:
                try:
                    status_result = await self.control('status')
                    status = status_result.get('result') if isinstance(status_result, dict) else None
                    adopted_authority = (
                        isinstance(status, dict)
                        and status.get('rd_control_mode') == 'pb_managed'
                        and status.get('adoption_state') == 'active'
                        and status.get('manual_state') == 'active')
                    if adopted_authority:
                        try:
                            cleanup_response = await self.control('d061_verified_stop')
                        except BaseException as exc:
                            cleanup_response = {'ok': False, 'error': type(exc).__name__,
                                                'detail': str(exc), 'ambiguous': True}
                        self.evidence['cleanup_typed_responses'] = {
                            'd061_verified_stop': cleanup_response}
                        payload = (cleanup_response.get('result')
                                   if isinstance(cleanup_response, dict) else None)
                        typed_stopped = (isinstance(cleanup_response, dict)
                                         and cleanup_response.get('ok') is True
                                         and isinstance(payload, dict)
                                         and payload.get('stopped') is True
                                         and payload.get('output') == 'off')
                except BaseException as exc:
                    self.evidence['cleanup_typed_responses'] = {
                        'status_error': {'type': type(exc).__name__, 'detail': str(exc)}}
            if not typed_stopped:
                try:
                    await self.client.turn_off()
                except BaseException:
                    pass
            try:
                off = await self.independent_off() is True
            except BaseException:
                off = False
            self.output_off_proven = off
            if off:
                clock = self.monotonic or time.monotonic
                self.evidence['physical_off'] = {
                    'monotonic_s': clock(),
                    'source': 'independent HA + native ESP SensorState containment proof',
                }
                self._record('physical-off-independently-confirmed', containment=True)
            lease_off = not self.lease_attempted
            if off and self.lease_attempted:
                try:
                    lease_off = await self._disarm_verified()
                except BaseException:
                    lease_off = False
            self.lease_disarmed = lease_off
            ownership_off = not self.production_stopped
            if off and lease_off and self.production_stopped:
                try:
                    ownership_off = await self._ownership_safe_after_off()
                except BaseException:
                    ownership_off = False
            # A canonical stop can return stopped=False when its immediate
            # switch ACK times out, even though independently observed OFF
            # arrives moments later. Do not forge an ACK or restore PB ownership.
            # Only the canonical coordinator's OFF_PENDING recovery may retire
            # its persisted Manual/adoption state after verified OFF + disarm.
            if (off and lease_off and self.production_stopped
                    and not ownership_off and self.acceptance_started
                    and callable(self.recover_off_pending)):
                try:
                    recovered = await asyncio.wait_for(
                        self.recover_off_pending(), timeout=15.0)
                    self.evidence['off_pending_recovery'] = {'acknowledged': recovered is True}
                    if recovered is True:
                        off = await self.independent_off() is True
                        self.output_off_proven = off
                        if off and self.lease_attempted:
                            lease_off = await self._disarm_verified()
                        self.lease_disarmed = lease_off
                        if off and lease_off:
                            ownership_off = await self._ownership_safe_after_off()
                except BaseException as exc:
                    self.evidence['off_pending_recovery'] = {
                        'acknowledged': False, 'error_type': type(exc).__name__}
            self.ownership_safe = ownership_off
            acceptance_off = not self.acceptance_started
            if self.acceptance_started:
                try:
                    await self.stop_acceptance()
                    acceptance_off = True
                    self.acceptance_started = False
                    self.acceptance_stopped = True
                except BaseException:
                    acceptance_off = False
            self.acceptance_stopped = acceptance_off
            if off and lease_off and ownership_off and acceptance_off and self.production_stopped and not self.restored:
                try:
                    restored = await self.restore_production()
                    if restored is not True:
                        return False
                    self.restored = True
                except BaseException:
                    return False
            self._cleanup_complete = off and lease_off and ownership_off and acceptance_off and (
                not self.production_stopped or self.restored)
            return self._cleanup_complete

    async def run(self):
        if self.duration_s != 20:
            raise RuntimeError('D061 positive-takeover smoke duration is fixed at 20 seconds')
        await self._fresh_off()
        if await self.independent_off() is not True:
            raise RuntimeError('preflight requires fresh independent HA and native Output OFF')
        battery_id = await self.locate_battery(BATTERY_NAME)
        if not battery_id:
            raise RuntimeError('Leoch 72Ah Ca/Ca battery record not found')
        self.evidence['battery_id'] = battery_id
        self._record('preflight-confirmed')
        try:
            state = await self.lease.read_state()
            remaining = getattr(state, 'remaining_s', None)
            slack = float(getattr(getattr(self.lease, 'config', None),
                                  'ack_remaining_slack_s', 15.0))
            if (getattr(state, 'armed', None) is not False
                    or getattr(state, 'tripped', None) is not False
                    or getattr(state, 'boot_quarantine', None) is not False
                    or isinstance(getattr(state, 'modbus_age_s', None), bool)
                    or not isinstance(getattr(state, 'modbus_age_s', None), (int, float))
                    or not math.isfinite(state.modbus_age_s)
                    or not 0 <= float(state.modbus_age_s) <= 20
                    or isinstance(remaining, bool)
                    or not isinstance(remaining, (int, float))
                    or not math.isfinite(remaining) or not 0 <= remaining <= slack):
                raise RuntimeError('preflight requires a healthy, unarmed edge lease')
            self.evidence['lease_preflight'] = {
                'armed': state.armed, 'tripped': state.tripped,
                'boot_quarantine': state.boot_quarantine,
                'generation': getattr(state, 'generation', None),
                'remaining_s': remaining, 'modbus_age_s': state.modbus_age_s,
            }
            self._record('lease-preflight-clear', generation=getattr(state, 'generation', None),
                         remaining_s=remaining)
            self.rollback_armed = True
            await self.stop_production()
            if not await self.verify_stopped():
                raise RuntimeError('production service stop was not verified')
            self.production_stopped = True
            self.lease_attempted = True
            if not await self.lease.arm():
                raise RuntimeError('canonical safety lease arm failed')
            armed_state = await self.lease.read_state()
            self.evidence['lease_armed'] = {
                'generation': getattr(armed_state, 'generation', None),
                'remaining_s': getattr(armed_state, 'remaining_s', None),
                'armed': getattr(armed_state, 'armed', None),
                'tripped': getattr(armed_state, 'tripped', None),
                'boot_quarantine': getattr(armed_state, 'boot_quarantine', None),
                'modbus_age_s': getattr(armed_state, 'modbus_age_s', None),
            }
            self._record('lease-armed', generation=getattr(armed_state, 'generation', None),
                         remaining_s=getattr(armed_state, 'remaining_s', None))
            await self._wait_for_on_dwell()
            result = await self.client.safe_enable_output(
                **TARGET, recipe_voltage_ceiling_v=14.7)
            if not bool(getattr(result, 'enabled', False)):
                raise RuntimeError('canonical safe enable rejected')
            await self._prove_on()

            self.lease.suspend_renewals()
            prepared = await self.lease.prepare_hands_off_release()
            released = await self.lease.release_to_hands_off(
                expected_generation=prepared.generation)
            self.released = True
            if (getattr(released, 'armed', None) is not False
                    or isinstance(getattr(released, 'generation', None), bool)
                    or not isinstance(getattr(released, 'generation', None), int)
                    or released.generation <= prepared.generation):
                raise RuntimeError('HANDS_OFF edge release acknowledgement invalid')
            release_state = await self.lease.read_state()
            if (getattr(release_state, 'armed', None) is not False
                    or getattr(release_state, 'generation', None) != released.generation
                    or getattr(release_state, 'tripped', None) is not False
                    or getattr(release_state, 'boot_quarantine', None) is not False):
                raise RuntimeError('HANDS_OFF edge release readback invalid')
            self.evidence['hands_off_release'] = {
                'generation': getattr(release_state, 'generation', None),
                'remaining_s': getattr(release_state, 'remaining_s', None),
                'armed': getattr(release_state, 'armed', None),
                'tripped': getattr(release_state, 'tripped', None),
                'boot_quarantine': getattr(release_state, 'boot_quarantine', None),
            }
            self._record('hands-off-release-ack',
                         generation=getattr(release_state, 'generation', None),
                         remaining_s=getattr(release_state, 'remaining_s', None))

            await self.bootstrap_hands_off()
            self.acceptance_started = True
            await self.start_acceptance()
            adopted = await self.control('d061_adopt_battery', battery_id=battery_id)
            self.evidence['typed_responses']['d061_adopt_battery'] = adopted
            if not adopted.get('ok'):
                raise RuntimeError('typed D061 adoption failed')
            if not await self.verify_state(TARGET):
                proof = getattr(self.verify_state, 'last_proof', None)
                if isinstance(proof, dict):
                    self.evidence['post_adoption_proof'] = proof
                    failed = ', '.join(proof.get('failed_predicates', [])) or 'unknown predicate'
                    raise RuntimeError('post-adoption proof failed: ' + failed)
                raise RuntimeError('post-adoption ownership, lease, protection, or setpoint proof failed')
            # A full typed status rebuild synchronously awaits many native ESP
            # lease entities. Repeating it every second can consume the whole
            # 20s window despite a proven PB_MANAGED adoption (real D061
            # evidence 2026-10-13). Keep the initial complete 20-predicate
            # verification above. During the bounded hold use fresh raw
            # readbacks while the canonical runtime safety task monitors
            # the physical lease and ownership continuously.
            clock = self.monotonic or asyncio.get_running_loop().time
            deadline = clock() + 20.0
            next_live_check = clock() + 4.0
            while True:
                remaining = deadline - clock()
                if remaining <= 0:
                    break
                # Do not race wait_for() against an identically long sleep:
                # normal scheduler jitter at the 20s boundary is not a fault.
                # Preserve a small OFF margin; a hung sleep still fails closed.
                if remaining <= 0.15:
                    break
                try:
                    await asyncio.wait_for(
                        self.sleep(min(1.0, remaining - 0.15)),
                        timeout=remaining)
                except asyncio.TimeoutError as exc:
                    if clock() >= deadline:
                        break
                    raise RuntimeError('takeover monitoring sleep stalled') from exc
                remaining = deadline - clock()
                if remaining <= 0:
                    break
                if clock() < next_live_check:
                    continue
                live = await asyncio.wait_for(self.client.get_all_live(),
                                              timeout=min(5.0, remaining))
                meta = live.get('_meta') or {}
                required = ('switch', 'output_state_code_v2', 'voltage', 'current',
                            'protection_code', 'temp_int', 'temp_ext',
                            'set_voltage_readback_v2', 'set_current_readback_v2',
                            'ovp_readback_v2', 'ocp_readback_v2')
                if not all(self._source_fresh(meta.get(key)) for key in required):
                    raise RuntimeError('D061 monitored source heartbeat stale or unavailable')
                if (str(live.get('switch')).strip().lower() != 'on'
                        or str(live.get('output_state_code_v2')).strip().lower()
                           not in ('1', '1.0', 'on')):
                    raise RuntimeError('D061 monitored Output ON proof lost')
                if not self._temperature_ok(live):
                    raise RuntimeError('D061 monitored battery or PSU temperature unsafe')
                protection = live.get('protection_code')
                if isinstance(protection, bool):
                    raise RuntimeError('D061 monitored raw protection invalid')
                try:
                    protection = float(protection)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise RuntimeError('D061 monitored raw protection invalid') from exc
                if not math.isfinite(protection) or protection != 0.0:
                    raise RuntimeError('D061 monitored hardware protection not NORMAL')
                fingerprint = {
                    'set_voltage_v': live.get('set_voltage_readback_v2'),
                    'set_current_a': live.get('set_current_readback_v2'),
                    'ovp_v': live.get('ovp_readback_v2'),
                    'ocp_a': live.get('ocp_readback_v2'),
                }
                if not fingerprint_matches(fingerprint, TARGET):
                    raise RuntimeError('D061 monitored setpoint fingerprint changed')
                self.evidence.setdefault('live_samples', []).append({
                    'monotonic_s': clock(),
                    'output_state': live.get('output_state_code_v2'),
                    'voltage_v': live.get('voltage'),
                    'current_a': live.get('current'),
                    'protection_code': protection,
                    'temp_int_psu_c': live.get('temp_int'),
                    'temp_ext_battery_c': live.get('temp_ext'),
                })
                next_live_check = clock() + 4.0
            stopped = await self.control('d061_verified_stop')
            self.evidence['typed_responses']['d061_verified_stop'] = stopped
            payload = stopped.get('result') if isinstance(stopped, dict) else None
            if (not isinstance(stopped, dict) or stopped.get('ok') is not True
                    or not isinstance(payload, dict)
                    or payload.get('stopped') is not True):
                raise RuntimeError('typed D061 verified stop failed or incomplete: adopted Manual authority not retired')
            if await self.independent_off() is not True:
                raise RuntimeError('independent OFF proof failed after typed stop')
            self.output_off_proven = True
            off_live = await self.client.get_all_live()
            off_meta = off_live.get('_meta') or {}
            if not all(self._source_fresh(off_meta.get(key)) for key in
                       ('voltage', 'current', 'protection_code', 'temp_int', 'temp_ext')):
                raise RuntimeError('final Output, protection, or temperature readback is stale')
            off_values = {}
            for key in ('voltage', 'current', 'protection_code'):
                value = off_live.get(key)
                if isinstance(value, bool):
                    raise RuntimeError('final physical readback is invalid: ' + key)
                try:
                    value = float(value)
                except (TypeError, ValueError, OverflowError):
                    raise RuntimeError('final physical readback is invalid: ' + key)
                if not math.isfinite(value):
                    raise RuntimeError('final physical readback is invalid: ' + key)
                off_values[key] = value
            if abs(off_values['voltage']) > .02 or abs(off_values['current']) > .02:
                raise RuntimeError('final Output voltage/current did not converge to zero')
            if off_values['protection_code'] != 0 or not self._temperature_ok(off_live):
                raise RuntimeError('final raw protection or temperature proof failed')
            final_setpoints = {
                'set_voltage_readback_v2': TARGET['voltage_v'],
                'set_current_readback_v2': TARGET['current_a'],
                'ovp_readback_v2': TARGET['ovp_v'],
                'ocp_readback_v2': TARGET['ocp_a'],
            }
            for key, target in final_setpoints.items():
                value = off_live.get(key)
                try:
                    value = float(value) if not isinstance(value, bool) else math.nan
                except (TypeError, ValueError, OverflowError):
                    value = math.nan
                if not math.isfinite(value) or abs(value - target) >= .02:
                    raise RuntimeError('final setpoint fingerprint changed: ' + key)
            off_clock = self.monotonic or time.monotonic
            self.evidence['physical_off'] = {
                'monotonic_s': off_clock(),
                'source': 'fresh HA voltage/current + HA SensorState + native ESP SensorState',
                'output_state': off_live.get('output_state_code_v2'),
                'output_voltage_v': off_values['voltage'],
                'output_current_a': off_values['current'],
                'set_voltage_v': off_live.get('set_voltage_readback_v2'),
                'set_current_a': off_live.get('set_current_readback_v2'),
                'ovp_v': off_live.get('ovp_readback_v2'),
                'ocp_a': off_live.get('ocp_readback_v2'),
                'raw_protection_code': off_values['protection_code'],
                'temp_int_psu_c': off_live.get('temp_int'),
                'temp_ext_battery_c': off_live.get('temp_ext'),
            }
            self._record('physical-off-independently-confirmed')
            self.released = False  # verified OFF permits ordinary lease disarm
            if not await self._disarm_verified():
                raise RuntimeError('edge lease containment was not acknowledged')
            self.lease_disarmed = True
            if not await self._ownership_safe_after_off():
                raise RuntimeError('post-stop PB ownership state was not verified safe')
            self.ownership_safe = True
            await self.stop_acceptance()
            self.acceptance_started = False
            self.acceptance_stopped = True
            if await self.restore_production() is not True:
                raise RuntimeError('production service restart was not verified')
            self.restored = True
            self._cleanup_complete = True
            return True
        except BaseException as exc:
            if self.rollback_armed:
                cleaned = await asyncio.shield(self._contain_and_restore())
                if not cleaned:
                    message = ('D061 containment is unresolved; Output OFF, lease disarm, '
                               'poller stop, and production restoration must be recovered manually; '
                               f'operation error: {exc}')
                    if isinstance(exc, asyncio.CancelledError):
                        exc.add_note(message)
                    else:
                        raise RuntimeError(message) from exc
            raise


async def run_d061_takeover_smoke(**dependencies):
    """Canonical Python entrypoint for a caller that has assembled dependencies."""
    return await D061TakeoverSmoke(**dependencies).run()


async def run_node104(stage, *, hooks=None):
    """Node-wide arbitration wraps the entire real physical acceptance lifecycle."""
    if hooks is not None:
        # The injected hooks are hardware-free unit-test fixtures.
        return await _run_node104_unlocked(stage, hooks=hooks)
    from .pairing import node104_acceptance_gate
    with node104_acceptance_gate():
        return await _run_node104_unlocked(stage, hooks=None)


async def _run_node104_unlocked(stage, *, hooks=None):
    """Wire the reviewed transaction to the isolated, staged node104 runtime.

    ``hooks`` exists for focused, hardware-free tests. Production callers use
    only canonical transports and the existing guarded composition.
    """
    stage = Path(stage).resolve()
    source = stage
    manifest = next((p for p in (stage / 'source-manifest.json',
                                  stage / 'manifest.json',
                                  stage / 'pairing-manifest.json') if p.is_file()), None)
    if manifest is None:
        raise RuntimeError('staged exact-source manifest unavailable')
    state = stage / 'state'
    state.mkdir(mode=0o700, exist_ok=True)
    if hooks is not None:
        return await _run_node104_hooks(stage, manifest, hooks)

    from .transient import require_node104
    require_node104()
    import sys
    sys.path.insert(0, str(source))
    # The remote process starts in stage/state. Seed the isolated ownership
    # file before importing/assembling the canonical bot composition.
    seed_isolated_hands_off_state(state)
    from . import pairing
    # Assemble only the staged source after verifying the supplied canonical manifest.
    composition, control, client = pairing.assemble(source, manifest,
        canonical=stage / '.canonical-source',
        attestation=stage / 'overlay-attestation.json')
    from .guard import Guard
    from .adapters import GuardedHassClient, GuardedHAConnector, GuardedESPConnector
    from runtime.config import load_config
    from config import HA_URL, HA_TOKEN
    from runtime.physical.transports.ha102 import HA102Transport
    from runtime.physical.transports.esp128 import ESPHomeTransport
    from physical_test_control import PhysicalTestControl

    # pairing.assemble binds the guarded canonical client; use its exact instance.
    require_hands_off_manager(getattr(composition.runtime, 'rd_control_mode_manager', None))
    config = load_config(source / 'config')
    safety = composition.runtime.runtime_safety_guard
    lease = safety.ensure_edge_safety_lease()
    if lease is None:
        raise RuntimeError('canonical edge safety lease unavailable')
    production_db = Path('/opt/services/rd6018-bot/state/rd6018.db')
    isolated_db = state / 'rd6018.db'
    if not production_db.is_file():
        raise RuntimeError('production database unavailable for read-only battery lookup')
    shutil.copy2(production_db, isolated_db)
    isolated_db.chmod(0o600)
    os.environ['RD6018_PHYSICAL_TEST_SOCKET'] = str(state / 'physical-test.sock')
    service = 'rd6018-bot.service'
    def service_state():
        raw = subprocess.check_output(['systemctl', 'show', service,
            '-p', 'ActiveState', '-p', 'MainPID'], text=True)
        return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
    initial_service = service_state()
    if initial_service.get('ActiveState') != 'active' or initial_service.get('MainPID', '0') == '0':
        raise RuntimeError('production service must be active before takeover handover')
    async def stop_production():
        await asyncio.to_thread(subprocess.run, ['systemctl', 'stop', service], check=True)
    async def verify_stopped():
        values = service_state()
        if values.get('ActiveState') != 'inactive' or values.get('MainPID') != '0':
            return False
        for process in Path('/proc').iterdir():
            if not process.name.isdigit():
                continue
            try:
                args = (process / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            except FileNotFoundError:
                continue
            if any(arg == 'bot.py' or arg.endswith('/bot.py') for arg in args):
                return False
        return True
    async def restore_production():
        await asyncio.to_thread(subprocess.run, ['systemctl', 'start', service], check=True)
        values = service_state()
        return values.get('ActiveState') == 'active' and values.get('MainPID', '0') != '0'
    async def bootstrap_hands_off():
        return None
    physical = PhysicalTestControl(composition.runtime, enabled=True,
        socket_path=str(state / 'physical-test.sock'))
    async def start_acceptance():
        nonlocal task
        task = asyncio.create_task(composition.run(physical_test_control=physical),
                                   name='d061-guarded-composition')
        # Wait until the in-process typed control dispatcher is live.
        for _ in range(100):
            if task.done():
                await task
            if physical._server is not None:
                return
            await asyncio.sleep(.1)
        raise RuntimeError('guarded composition did not start physical control')
    async def stop_acceptance():
        if task is None:
            return
        if task.done():
            if task.cancelled():
                return
            error = task.exception()
            if error is not None:
                raise RuntimeError('acceptance composition exited with an error') from error
            raise RuntimeError('acceptance composition exited before supervised stop')
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if not task.done() or not task.cancelled():
            raise RuntimeError('acceptance composition cancellation was not confirmed')
    async def typed(op, **kwargs):
        return await control.dispatch({'op': op, **kwargs})
    async def locate_battery(name):
        # The canonical registry is read-only here; source DB was copied first.
        conn = sqlite3.connect('file:' + str(isolated_db) + '?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return select_leoch_battery(conn, name)
        finally:
            conn.close()
    async def verify_state(target):
        result = await typed('status')
        status = result.get('result', result)
        live = await client.get_all_live()
        lease_state = await lease.read_state()
        guard = getattr(client, 'guard', None)
        def number(value):
            if isinstance(value, bool):
                return None
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError):
                return None
            return value if math.isfinite(value) else None
        def close(actual, expected):
            actual = number(actual)
            return actual is not None and abs(actual - expected) < .02
        edge_lease = status.get('edge_lease') if isinstance(status, dict) else {}
        edge_lease = edge_lease if isinstance(edge_lease, dict) else {}
        protection = status.get('protection') if isinstance(status, dict) else {}
        protection = protection if isinstance(protection, dict) else {}
        meta = live.get('_meta') or {}
        guard_report = getattr(guard, 'last_report', None)
        guard_age = None if guard_report is None else time.monotonic() - guard_report
        try:
            modbus_age = number(getattr(lease_state, 'modbus_age_s', None))
            remaining = number(getattr(lease_state, 'remaining_s', None))
        except Exception:
            modbus_age = remaining = None
        fingerprint = status.get('fingerprint') if isinstance(status, dict) else None
        fingerprint = fingerprint if isinstance(fingerprint, dict) else {}
        checks = {
            'pb_managed': isinstance(status, dict) and status.get('rd_control_mode') == 'pb_managed',
            'adoption_active': isinstance(status, dict) and status.get('adoption_state') == 'active',
            'output_on_dual_source': (
                isinstance(status, dict) and str(status.get('output', '')).lower() == 'on'
                and str(status.get('output_state_code_v2', '')).strip() in ('1', '1.0')
                and str(live.get('switch', '')).lower() == 'on'
                and str(live.get('output_state_code_v2', '')).strip() in ('1', '1.0')
                and D061TakeoverSmoke._source_fresh(meta.get('switch'))
                and D061TakeoverSmoke._source_fresh(meta.get('output_state_code_v2'))),
            'fingerprint_within_tolerance': fingerprint_matches(fingerprint, target),
            'guard_fresh': (getattr(guard, 'state', None) is True
                and guard_age is not None and math.isfinite(guard_age) and 0 <= guard_age <= 8),
            'edge_lease_armed': edge_lease.get('armed') is True,
            'edge_lease_not_tripped': edge_lease.get('tripped') is False,
            'edge_lease_not_quarantined': edge_lease.get('boot_quarantine') is False,
            'lease_armed': getattr(lease_state, 'armed', None) is True,
            'lease_not_tripped': getattr(lease_state, 'tripped', None) is False,
            'lease_not_quarantined': getattr(lease_state, 'boot_quarantine', None) is False,
            'lease_modbus_fresh': modbus_age is not None and 0 <= modbus_age <= 20,
            'lease_remaining_fresh': remaining is not None and 0 < remaining <= 900,
            'raw_protection_normal': (number(protection.get('code')) == 0
                and number(protection.get('age_s')) is not None
                and 0 <= number(protection.get('age_s')) <= 8),
            'setpoint_readback_voltage_v': (close(live.get('set_voltage_readback_v2'), target['voltage_v'])
                and D061TakeoverSmoke._source_fresh(meta.get('set_voltage_readback_v2'))),
            'setpoint_readback_current_a': (close(live.get('set_current_readback_v2'), target['current_a'])
                and D061TakeoverSmoke._source_fresh(meta.get('set_current_readback_v2'))),
            'setpoint_readback_ovp_v': (close(live.get('ovp_readback_v2'), target['ovp_v'])
                and D061TakeoverSmoke._source_fresh(meta.get('ovp_readback_v2'))),
            'setpoint_readback_ocp_a': (close(live.get('ocp_readback_v2'), target['ocp_a'])
                and D061TakeoverSmoke._source_fresh(meta.get('ocp_readback_v2'))),
            'safe_temperature': D061TakeoverSmoke._temperature_ok(live),
        }
        proof = {
            'typed_status': {key: status.get(key) for key in (
                'rd_control_mode', 'adoption_state', 'manual_state', 'output',
                'output_state_code_v2', 'fingerprint', 'edge_lease', 'protection')}
                if isinstance(status, dict) else status,
            'lease_state': {'armed': getattr(lease_state, 'armed', None),
                'tripped': getattr(lease_state, 'tripped', None),
                'boot_quarantine': getattr(lease_state, 'boot_quarantine', None),
                'remaining_s': remaining, 'modbus_age_s': modbus_age},
            'guard_state': getattr(guard, 'state', None), 'guard_last_report_age_s': guard_age,
            'live_setpoints': {key: live.get(key) for key in (
                'set_voltage_readback_v2', 'set_current_readback_v2',
                'ovp_readback_v2', 'ocp_readback_v2')},
            'live_output': {key: live.get(key) for key in ('switch', 'output_state_code_v2')},
            'checks': checks, 'failed_predicates': [key for key, passed in checks.items() if not passed],
        }
        tx.evidence['post_adoption_proof'] = proof
        verify_state.last_proof = proof
        return all(checks.values())
    async def independent_off():
        ha = HA102Transport(config.transports['ha102'], config.rd)
        esp = ESPHomeTransport(config.transports['esp128'], config.rd)
        try:
            return await independent_output_off(
                ha, esp, config.transports['ha102'].entities.get('output_state'),
                voltage_entity=config.transports['ha102'].entities.get('voltage'),
                current_entity=config.transports['ha102'].entities.get('current'))
        finally:
            close_results = await asyncio.gather(
                ha.close(), esp.close(), return_exceptions=True)
            if any(isinstance(result, BaseException) for result in close_results):
                raise RuntimeError('independent OFF transport close failed')

    async def recover_off_pending():
        # Invoke the original coordinator's OFF-only restart containment API,
        # never a synthetic ownership transition. D061TakeoverSmoke calls this
        # only after independent OFF and lease-disarm readback are positive.
        coordinator = getattr(composition.runtime, 'rd_managed_live_adoption', None)
        if coordinator is None or getattr(coordinator, 'off_pending', None) is not True:
            return False
        return await coordinator.recover_startup() is True

    task = None
    tx = D061TakeoverSmoke(client=client, lease=lease,
        stop_production=stop_production, verify_stopped=verify_stopped,
        bootstrap_hands_off=bootstrap_hands_off, start_acceptance=start_acceptance,
        control=typed, locate_battery=locate_battery, verify_state=verify_state,
        stop_acceptance=stop_acceptance, independent_off=independent_off,
        restore_production=restore_production,
        recover_off_pending=recover_off_pending)
    evidence_path = state / 'd061-takeover-result.json'
    def persist_evidence(result, error_type=None):
        evidence = {
            'result': result,
            'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
            'error_type': error_type,
            'independent_output_off': tx.output_off_proven,
            'edge_lease_disarmed': tx.lease_disarmed,
            'ownership_safe': tx.ownership_safe,
            'acceptance_poller_stopped': tx.acceptance_stopped,
            'production_restored': tx.restored,
            'containment_complete': tx._cleanup_complete,
            **tx.evidence,
        }
        temp = evidence_path.with_suffix('.tmp')
        temp.write_text(json.dumps(evidence, sort_keys=True) + '\n', encoding='utf-8')
        temp.chmod(0o600)
        temp.replace(evidence_path)
        evidence_path.chmod(0o600)
        print(json.dumps(evidence, sort_keys=True))
    try:
        result = await tx.run()
        if result is not True:
            raise RuntimeError('takeover transaction did not return a positive PASS')
        persist_evidence('PASS')
        return True
    except BaseException as exc:
        persist_evidence('FAIL', type(exc).__name__)
        raise
    finally:
        if task is not None and not task.done():
            await stop_acceptance()


async def _run_node104_hooks(stage, manifest, hooks):
    """Test seam which still requires the exact pairing assembly call."""
    state_path = seed_isolated_hands_off_state(Path(stage) / 'state')
    assemble = hooks['assemble']
    assembled = assemble(stage, manifest)
    if not assembled:
        raise RuntimeError('staged source assembly failed')
    manager = getattr(assembled, 'rd_control_mode_manager', None)
    if manager is not None:
        require_hands_off_manager(manager)
    return await hooks['run'](stage, manifest, assembled)
