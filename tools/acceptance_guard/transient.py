"""Fail-closed, supervised transient D061 acceptance transaction.

This is an orchestration wrapper around the existing guarded production client
and edge lease. It deliberately provides no raw HA/ESP actuator operation.
"""
import asyncio
import argparse
import fcntl
import math
import os
from pathlib import Path
import socket
import subprocess


MAX_PROGRAMMED_V = 15.5
LEOCH_CACAC_NORMAL_V = 14.7
PSU_TEMP_INTRINSIC_CUTOFF_C = 55.0
_OFF = ('off', 'false', '0')
_ON = ('on', 'true', '1')
_NODE104_HOSTNAME = 'rd6018-bot'
_NODE104_MACHINE_ID = 'd2a570f751e14d8cbc654b5c4559ce24'


def require_node104():
    """Refuse to operate local systemd/proc unless this is the pinned node."""
    try:
        machine_id = Path('/etc/machine-id').read_text().strip()
    except OSError as exc:
        raise RuntimeError('transient executor requires the exact node104 host') from exc
    if (socket.gethostname() != _NODE104_HOSTNAME or os.geteuid() != 0
            or machine_id != _NODE104_MACHINE_ID):
        raise RuntimeError('transient executor requires root on the exact node104 machine')


class TransientAcceptance:
    def __init__(self, *, client, lease, stop_production, verify_stopped,
                 prove_single_owner, restore_production, independent_off,
                 target, duration_s, sleep=asyncio.sleep, monotonic=None):
        self.client, self.lease = client, lease
        self.stop_production, self.verify_stopped = stop_production, verify_stopped
        self.prove_single_owner, self.restore_production = prove_single_owner, restore_production
        self.independent_off, self.target = independent_off, dict(target)
        self.duration_s, self.sleep = float(duration_s), sleep
        self.monotonic = monotonic
        self._rollback_armed = False
        self._production_stopped = False
        self._lease_acquired = False
        self._lease_attempted = False
        self._cleanup_lock = asyncio.Lock()
        self._cleaned = False
        self._off_proven = False
        self._restored = False
        self._cleanup_error = None

    @staticmethod
    def _source_fresh(meta, key):
        row = meta.get(key) or {}
        try:
            age = float(row['age_s'])
        except (KeyError, TypeError, ValueError):
            return False
        return (str(row.get('status', '')).lower() == 'ok'
                and math.isfinite(age) and 0 <= age <= 8)

    async def _fresh_off_preflight(self):
        live = await self.client.get_all_live()
        meta = live.get('_meta') or {}
        if not all(self._source_fresh(meta, key) for key in ('switch', 'output_state_code_v2')):
            raise RuntimeError('fresh dual-source Output OFF preflight unavailable')
        if str(live.get('switch', '')).strip().lower() not in _OFF:
            raise RuntimeError('dual-source preflight requires Output OFF')
        code = live.get('output_state_code_v2')
        if isinstance(code, bool) or str(code).strip().lower() not in ('0', '0.0', 'off'):
            raise RuntimeError('dual-source preflight reports Output ON or unknown')
        self._require_temperature(live, pre_enable=True)
        self._require_raw_protection_normal(live)

    def _require_raw_protection_normal(self, live):
        """Validate protection register and freshness from the canonical live snapshot."""
        meta = live.get('_meta') or {}
        value = live.get('protection_code')
        if isinstance(value, bool):
            raise RuntimeError('canonical raw protection telemetry is invalid or stale')
        try:
            code = float(value)
        except (TypeError, ValueError, OverflowError):
            raise RuntimeError('canonical raw protection telemetry is invalid or stale')
        if not math.isfinite(code) or code != 0:
            raise RuntimeError('raw RD6018 protection status is not NORMAL')
        if not self._source_fresh(meta, 'protection_code'):
            raise RuntimeError('canonical raw protection telemetry is invalid or stale')

    def _require_temperature(self, live, *, pre_enable=False):
        """Acceptance-only thermal interlock; PSU and battery probes stay distinct."""
        meta = live.get('_meta') or {}
        for key, label in (('temp_int', 'PSU/block'), ('temp_ext', 'battery')):
            if not self._source_fresh(meta, key):
                raise RuntimeError(f'{label} temperature telemetry is invalid or stale')
            value = live.get(key)
            if isinstance(value, bool):
                raise RuntimeError(f'{label} temperature telemetry is invalid or stale')
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError):
                raise RuntimeError(f'{label} temperature telemetry is invalid or stale')
            if not math.isfinite(value) or value < -20 or value > 100:
                raise RuntimeError(f'{label} temperature telemetry is invalid or stale')
            # 38 C is a prior-run observation, not a limit. Match the
            # canonical ESPHome intrinsic local PSU/block cutoff at 55 C.
            if key == 'temp_int' and value >= PSU_TEMP_INTRINSIC_CUTOFF_C:
                raise RuntimeError('PSU/block temperature reached 55 C intrinsic cutoff')
    def _require_healthy_lease(self, state):
        remaining = getattr(state, 'remaining_s', None)
        raw_modbus_age = getattr(state, 'modbus_age_s', None)
        if (isinstance(remaining, bool) or isinstance(raw_modbus_age, bool)
                or not isinstance(getattr(state, 'armed', None), bool)
                or not isinstance(getattr(state, 'tripped', None), bool)
                or not isinstance(getattr(state, 'boot_quarantine', None), bool)):
            raise RuntimeError('canonical safety lease state is invalid')
        try:
            remaining = float(remaining)
            modbus_age = float(raw_modbus_age)
        except (TypeError, ValueError, AttributeError):
            raise RuntimeError('canonical safety lease state is invalid')
        ttl = float(getattr(getattr(self.lease, 'config', None), 'lease_ttl_s', 900.0))
        if (getattr(state, 'armed', None) is not True
                or getattr(state, 'tripped', None) is not False
                or getattr(state, 'boot_quarantine', None) is not False
                or not math.isfinite(modbus_age) or modbus_age < 0 or modbus_age > 20
                or not math.isfinite(remaining) or remaining <= 0
                or not math.isfinite(ttl) or ttl <= 0 or remaining > ttl):
            raise RuntimeError('canonical safety lease is unhealthy')

    async def _wait_for_ordinary_on_dwell(self):
        """Earn the guard's complete 12 s OFF dwell before asking it to turn ON."""
        guard = getattr(self.client, 'guard', None)
        deadline = asyncio.get_running_loop().time() + 45.0
        while True:
            live = await self.client.get_all_live()
            meta = live.get('_meta') or {}
            if (not all(self._source_fresh(meta, key)
                        for key in ('switch', 'output_state_code_v2'))
                    or str(live.get('switch', '')).strip().lower() not in _OFF
                    or str(live.get('output_state_code_v2', '')).strip().lower() not in ('0', '0.0', 'off')):
                raise RuntimeError('dual-source OFF evidence lost before guarded enable')
            self._require_raw_protection_normal(live)
            self._require_temperature(live, pre_enable=True)
            if guard is None:
                return  # Injected test clients may model the dwell contract at the sink.
            try:
                guard.require_transition(True)
                return
            except Exception as exc:
                if exc.__class__.__name__ != 'Blocked':
                    raise
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError('12 second fresh OFF dwell was not established')
            await self.sleep(0.5)

    async def _cleanup(self):
        async with self._cleanup_lock:
            if self._cleaned:
                return self._off_proven
            failures = []
            try:
                await self.client.turn_off()
            except BaseException as exc:
                failures.append(f'Output OFF request failed: {exc}')
            try:
                self._off_proven = bool(await self.independent_off())
            except BaseException as exc:
                self._off_proven = False
                failures.append(f'independent OFF proof failed: {exc}')
            if not self._off_proven:
                failures.append('independent OFF proof did not confirm Output OFF')
            lease_released = not self._lease_attempted
            if self._off_proven and self._lease_attempted:
                try:
                    lease_released = bool(await self.lease.disarm())
                except BaseException as exc:
                    lease_released = False
                    failures.append(f'lease disarm failed: {exc}')
                if not lease_released:
                    failures.append('lease disarm was not acknowledged')
                if lease_released:
                    self._lease_acquired = False
                    self._lease_attempted = False
            # OFF must be independently proven and lease release acknowledged.
            # The canonical OFF result is not itself the independent proof.
            if self._off_proven and lease_released and self._production_stopped and not self._restored:
                try:
                    await self.restore_production()
                    self._restored = True
                except BaseException as exc:
                    failures.append(f'production restore failed: {exc}')
            self._cleaned = self._off_proven and lease_released and (
                not self._production_stopped or self._restored)
            self._cleanup_error = None if self._cleaned else '; '.join(failures)
            return self._cleaned

    def _validate_target(self):
        try:
            v, current = float(self.target['voltage_v']), float(self.target['current_a'])
            ovp, ocp = float(self.target['ovp_v']), float(self.target['ocp_a'])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError('invalid safe target') from exc
        if not all(math.isfinite(x) and x > 0 for x in (v, current, ovp, ocp)):
            raise RuntimeError('target values must be finite and positive')
        if v > MAX_PROGRAMMED_V or v > LEOCH_CACAC_NORMAL_V:
            raise RuntimeError('target exceeds Leoch Ca/Ca ordinary authority')
        if ovp > MAX_PROGRAMMED_V or ovp <= v:
            raise RuntimeError('OVP must exceed target voltage and not exceed 15.5 V')
        if ocp <= current:
            raise RuntimeError('OCP must remain above the requested current')
        return v, current, ovp, ocp

    async def run(self):
        if (not math.isfinite(self.duration_s) or self.duration_s <= 0
                or self.duration_s > 900):
            raise RuntimeError('acceptance duration must be in (0, 900] seconds')
        target = self._validate_target()
        try:
            await self._fresh_off_preflight()
        except BaseException:
            # A stale/mismatched preflight must converge Output OFF even when
            # production is still running and no lease has been acquired.
            try:
                await self.client.turn_off()
            except BaseException:
                pass
            raise
        # Rollback is armed before any production ownership/isolation action.
        self._rollback_armed = True
        try:
            await self.stop_production()
            if not await self.verify_stopped():
                raise RuntimeError('production service did not stop and verify')
            self._production_stopped = True
            if not await self.prove_single_owner():
                raise RuntimeError('single-owner/no-competing-poller proof failed')
            self._lease_attempted = True
            if not await self.lease.arm():
                raise RuntimeError('canonical safety lease acquisition failed')
            self._lease_acquired = True
            await self._wait_for_ordinary_on_dwell()
            self._require_temperature(await self.client.get_all_live(), pre_enable=True)
            result = await self.client.safe_enable_output(
                voltage_v=target[0], current_a=target[1], ovp_v=target[2],
                ocp_a=target[3], recipe_voltage_ceiling_v=LEOCH_CACAC_NORMAL_V)
            if not bool(getattr(result, 'enabled', False)):
                raise RuntimeError('canonical safe enable rejected')
            # The live window is wall-clock bounded. A tick includes readback
            # and lease renewal, not only the scheduled sleep interval. Keep the
            # virtual countdown as well so unit-test injected sleeps can advance
            # without consuming real wall time.
            clock = self.monotonic or asyncio.get_running_loop().time
            deadline = clock() + self.duration_s
            remaining = self.duration_s
            while remaining > 0:
                interval = min(1.0, remaining)
                try:
                    await asyncio.wait_for(self.sleep(interval), timeout=interval + 1.0)
                except asyncio.TimeoutError as exc:
                    raise RuntimeError('acceptance window timeout') from exc
                remaining -= interval
                live = await self.client.get_all_live()
                meta = live.get('_meta') or {}
                if (not all(self._source_fresh(meta, key)
                            for key in ('switch', 'output_state_code_v2'))
                        or str(live.get('switch', '')).strip().lower() not in _ON
                        or str(live.get('output_state_code_v2', '')).strip().lower() not in ('1', '1.0', 'on')):
                    raise RuntimeError('Output telemetry lost or dual-source state mismatch')
                self._require_raw_protection_normal(live)
                self._require_temperature(live)
                renew = getattr(self.lease, 'renew_if_due', None)
                if not callable(renew):
                    raise RuntimeError('canonical safety lease renewal API unavailable')
                try:
                    lease_state = await renew()
                except Exception as exc:
                    raise RuntimeError('canonical safety lease renewal failed') from exc
                self._require_healthy_lease(lease_state)
                remaining = min(remaining, max(0.0, deadline - clock()))
            if not await asyncio.shield(self._cleanup()):
                raise RuntimeError(f'cleanup failed: {self._cleanup_error}')
            return True
        except BaseException as exc:
            if self._rollback_armed:
                cleaned = await asyncio.shield(self._cleanup())
                if not cleaned and not isinstance(exc, asyncio.CancelledError):
                    raise RuntimeError(f'operation failed and cleanup failed: {self._cleanup_error}') from exc
            raise
        finally:
            if self._rollback_armed and not self._cleaned:
                await asyncio.shield(self._cleanup())

    async def recover_contained(self):
        """Prove OFF, release the lease, and restore production without enabling."""
        await self._fresh_off_preflight()
        self._rollback_armed = True
        try:
            self._lease_attempted = True
            if not await self.lease.arm():
                raise RuntimeError('canonical safety lease acquisition failed')
            self._lease_acquired = True
            await self.client.turn_off()
            if not await asyncio.shield(self._cleanup()):
                raise RuntimeError(f'cleanup failed: {self._cleanup_error}')
            return True
        except BaseException as exc:
            if self._rollback_armed:
                cleaned = await asyncio.shield(self._cleanup())
                if not cleaned and not isinstance(exc, asyncio.CancelledError):
                    raise RuntimeError(f'recovery failed and cleanup failed: {self._cleanup_error}') from exc
            raise
        finally:
            if self._rollback_armed and not self._cleaned:
                await asyncio.shield(self._cleanup())


def main():
    """Run the reviewed supervised window through canonical production adapters."""
    parser = argparse.ArgumentParser(description='Supervised D061 transient acceptance window')
    parser.add_argument('--voltage-v', type=float, required=True)
    parser.add_argument('--current-a', type=float, required=True)
    parser.add_argument('--ovp-v', type=float, required=True)
    parser.add_argument('--ocp-a', type=float, required=True)
    parser.add_argument('--duration-s', type=float, required=True)
    parser.add_argument('--confirm-physical-preflight', action='store_true')
    parser.add_argument('--confirm-cutoff-tested', action='store_true')
    parser.add_argument('--confirm-temperature-sensor', action='store_true')
    parser.add_argument('--confirm-supervised', action='store_true')
    parser.add_argument('--contained-recovery', action='store_true')
    args = parser.parse_args()
    if not all((args.confirm_physical_preflight, args.confirm_cutoff_tested,
                args.confirm_temperature_sensor, args.confirm_supervised)):
        parser.error('all current physical readiness acknowledgements are required')
    asyncio.run(_run_cli(args))


async def _run_cli(args):
    # This executor calls local systemctl and inspects local /proc. Validate the
    # execution host before importing production adapters or reading credentials.
    require_node104()
    from .adapters import GuardedHassClient, GuardedHAConnector, GuardedESPConnector
    from runtime.physical.transports.ha102 import HA102Transport
    from runtime.physical.transports.esp128 import ESPHomeTransport
    from .guard import Guard
    from edge_safety_lease import EdgeSafetyLease
    from runtime.config import load_config
    from config import HA_URL, HA_TOKEN

    source = Path(__file__).resolve().parents[2]
    config = load_config(source / 'config')
    guard = Guard(voltage_ceiling=LEOCH_CACAC_NORMAL_V)
    connector_type = {'esp_direct': GuardedESPConnector, 'ha_esp': GuardedHAConnector}.get(config.default_connector)
    if connector_type is None:
        raise RuntimeError('acceptance requires the configured canonical physical connector')
    connector = connector_type(config, guard)
    client = GuardedHassClient(HA_URL, HA_TOKEN, guard=guard, backend=connector)
    lease = EdgeSafetyLease(client)
    service = 'rd6018-bot.service'

    def service_state():
        raw = subprocess.check_output(['systemctl', 'show', service, '-p', 'ActiveState', '-p', 'MainPID'], text=True)
        return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)

    initial = service_state()
    contained_recovery = bool(args.contained_recovery)
    if contained_recovery:
        if initial.get('ActiveState') != 'inactive' or initial.get('MainPID', '0') != '0':
            raise RuntimeError('contained recovery requires inactive service with MainPID 0')
    elif initial.get('ActiveState') != 'active' or initial.get('MainPID', '0') == '0':
        raise RuntimeError('expected active production rd6018-bot.service owner')

    async def stop():
        await asyncio.to_thread(subprocess.run, ['systemctl', 'stop', service], check=True)

    async def stopped():
        state = service_state()
        return state.get('ActiveState') == 'inactive' and state.get('MainPID') == '0'

    async def sole_owner():
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                argv = (entry / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            except (FileNotFoundError, PermissionError):
                continue
            if any(arg == 'bot.py' or arg.endswith('/bot.py') for arg in argv):
                return False
        return True

    async def restore():
        await asyncio.to_thread(subprocess.run, ['systemctl', 'start', service], check=True)

    # Separate transport instances establish genuinely independent HA and
    # ESPHome observations. Two entities from get_all_live() are one source.
    ha_proof = HA102Transport(config.transports['ha102'], config.rd)
    esp_proof = ESPHomeTransport(config.transports['esp128'], config.rd)

    async def independent_off():
        ha_entity = config.transports['ha102'].entities.get('output_state')
        esp_entity = config.transports['esp128'].entities.get('output_state')
        if not ha_entity or not esp_entity:
            return False
        ha = await ha_proof._get(ha_entity)
        ha_stamp = ha.get('last_reported') or ha.get('last_updated')
        try:
            ha_age = max(0.0, __import__('time').time() - __import__('datetime').datetime.fromisoformat(
                ha_stamp.replace('Z', '+00:00')).timestamp())
        except (AttributeError, TypeError, ValueError):
            return False
        esp_value, esp_meta = await esp_proof.get_physical_output_report()
        ha_state = str(ha.get('state', '')).strip().lower()
        return (ha_age <= 8 and ha_state in _OFF
                and esp_meta.get('status') == 'ok'
                and esp_meta.get('native_type') == 'SensorState'
                and isinstance(esp_meta.get('age_s'), (int, float))
                and 0 <= esp_meta['age_s'] <= 8
                and esp_meta.get('subscription_timestamp_monotonic') is not None
                and not isinstance(esp_value, bool)
                and esp_value == 0)

    # Share the exact same node104 lock with bot-level D061 takeover.
    # It remains held until OFF, lease release and production recovery finish.
    from .pairing import node104_acceptance_gate
    with node104_acceptance_gate():
        tx = TransientAcceptance(client=client, lease=lease, stop_production=stop,
            verify_stopped=stopped, prove_single_owner=sole_owner,
            restore_production=restore, independent_off=independent_off,
            target={'voltage_v': args.voltage_v, 'current_a': args.current_a,
                    'ovp_v': args.ovp_v, 'ocp_a': args.ocp_a},
            duration_s=args.duration_s)
        try:
            if contained_recovery:
                # The service was independently required to be inactive at entry;
                # successful OFF proof and lease release authorize its restoration.
                tx._production_stopped = True
                await tx.recover_contained()
            else:
                await tx.run()
        finally:
            await client.close()
            await ha_proof.close()
            await esp_proof.close()


if __name__ == '__main__':
    main()
