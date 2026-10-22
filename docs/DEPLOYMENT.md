# Deployment and rollback runbook

## Mandatory live-node preflight — direct ESP first

**Always obtain NEW, CURRENT physical data directly from ESP Native API**;
see `docs/ESP_NATIVE_LIVE_EVIDENCE.md`. Before any node104 service stop,
prepare/activate/recover, or START, obtain direct ESP R18, measured U/I,
battery voltage, setpoints, R16/OVP/OCP, armed/generation/remaining,
trip/quarantine/autonomous and Modbus age. Use the existing ESP-direct
collector with source/type/device-identity/timestamp checks. Do not use
HA102 readings or an old saved report in place of fresh native callbacks.

When stopping the service for a versioned release, reacquire **a distinct
post-stop fresh Native ESP OFF proof**, in addition to the pre-stop proof,
as required by the pinned transaction owner. HA102 may corroborate but is
never the authoritative physical source. TCP connectivity is not telemetry.
Native acquisition failure means `ESP ACCESS BLOCKED`, not permission to
deploy without fresh ESP evidence. Read-only Native API diagnostics are not
hardware writes; all changes remain under the single existing ExecutionPort.


This document is for replacing the bot on an existing node. It intentionally does not prescribe a new service layout: discover and preserve the node's current runtime, virtualenv and service manager.

## Production model

Normal production launch:

```bash
python bot.py
```

`bot.py` is the sole production entrypoint. It composes `runtime.production_runtime`; retired runtime facades have been removed.

Production controller:

```text
ProductionChargeController
  -> ManagedChargeController authority for non-Custom Main/Mix
  -> legacy safety/mechanics scaffold
  -> recipe envelope
  -> SafeOutputCoordinator / strict runtime safety
  -> renewable ESPHome edge safety lease
  -> RD6018 via Home Assistant / direct local Modbus
```

The production safety lease is a dead-man contract, not an optional dashboard feature. Before any controller-managed Output ON, the bot requires a positively acknowledged local lease. The production contract is a 900-second local TTL renewed every 300 seconds. If bot/API communication disappears completely, the ESPHome node must be able to turn RD6018 Output OFF locally when that lease expires. With `esp_direct`, lease state and button commands use the native ESPHome Noise API directly; Home Assistant is not required for the lease path and remains only a compatibility sidecar when configured.

See `docs/RD6018_FAILSAFE.md` and `esphome/rd6018_safety_lease.yaml`.

## Before deployment

On the node, determine rather than assume:

```bash
pwd
systemctl list-units --type=service | grep -i rd6018
systemctl cat <service-name>
ps aux | grep -E '[p]ython.*bot\.py|[p]ython.*bot_legacy\.py'
```

Record:

- current working directory;
- service name and unit definition;
- Python executable / virtualenv;
- current git branch and SHA;
- current `.env` and any service-level environment overrides;
- writable runtime files/database location;
- actual ESPHome RD6018 controller configuration/model and its current firmware/config backup.

Do not print secrets into reports.

## Mandatory deployment order: edge failsafe first

`RD6018_EDGE_LEASE_REQUIRED=1` is the production default. Therefore do **not** deploy the bot code and assume charging will continue normally before the edge package exists. Missing/invalid lease entities intentionally make Output ON fail closed.

Before replacing the running bot:

1. Back up the current ESPHome configuration/firmware for the RD6018 controller.
2. Merge/include `esphome/rd6018_safety_lease.yaml` into the actual node configuration.
3. Compile that exact real node configuration. A repository unit test is not an ESPHome schema/compiler substitute.
4. Flash/update the ESPHome node while RD6018 Output is OFF and no battery recovery/HV stage is active.
5. Verify the six lease entities exist and are updating:
   - `button.rd_6018_safety_lease_renew`
   - `button.rd_6018_safety_lease_disarm`
   - `binary_sensor.rd_6018_safety_lease_armed`
   - `sensor.rd_6018_safety_lease_generation`
   - `sensor.rd_6018_safety_modbus_age`
   - `sensor.rd_6018_safety_lease_remaining`
6. Verify `Safety Modbus Age` repeatedly returns to a small value. The reference rdtech ESPHome controller polls Modbus every 5 s; the production lease rejects a direct-Modbus age over 20 s.
7. With RD6018 Output OFF, press Renew once and verify:
   - generation increments;
   - armed becomes ON;
   - remaining jumps to approximately 900 s;
   - direct Modbus remains fresh.
8. Press Disarm with Output still OFF and verify armed becomes OFF.

Do not proceed to bot deployment if any of these checks fail.

## Backup

Before modifying the working tree, preserve a quick rollback target. At minimum record the deployed SHA:

```bash
git rev-parse HEAD
git status --short
```

If the deployed tree contains local operational files or uncommitted configuration, back up the complete directory or the relevant local files before checkout/reset. Do not discard local `.env`, SQLite databases, session JSON or service overrides.

## Offline node104 transaction-preparation harness

`tools/node104_atomic_deploy.py` is an offline preparation and simulation tool;
it does not activate production, invoke SSH/systemd, control the RD6018, or
perform OTA/lease operations. Its simulator requires an initialized temporary
simulation root and enforces root-contained ordinary directories on one
filesystem. Release metadata and journal updates are written atomically;
backup files and nested directories are flushed before the journal can mark the
backup durable.

Recovery is fail-closed. It takes an OS-held exclusive lock (including over a
stale lock marker left by a crashed process), validates the journal identity,
root-contained backup path, backup manifest, and filesystem state, then restores
the pre-image idempotently. Missing/corrupt backups, path traversal, malformed
journals, impossible rename states, and uninitialized or arbitrary CLI roots
are blocked. Green simulation tests are software evidence only and do not
authorize deployment or physical validation.

## D146: recover a Python release while preserving live state

Use the existing D090 transaction owner and its existing node104 service. This
path is for a journaled Python release recovery where current
`charge_session.json` and an active D084 `session_recovery_quarantine.json`
must survive. It restores the journaled `app/`, `venv/`, `.env` and deployment
marker under D090's existing journal/backup checks. It never restores
`state/` from the historical backup. The durable recovery journal records the
exact post-stop state inventory before code replacement.

Before running recovery, the existing owner must:

1. Capture a new direct ESP Native subscription and verify matching device
   identity, fresh `SensorState` R18 OFF and zero measured U/I, fresh edge
   callbacks showing lease disarmed, no trip/boot quarantine/autonomous mode,
   900 s lease TTL and Modbus age at most 20 s. Read R16, setpoints, OVP/OCP
   and battery voltage as documented in `ESP_NATIVE_LIVE_EVIDENCE.md`.
2. Confirm the existing service is active with one positive MainPID and stable
   at the journal's pinned source or old SHA. Recovery takes a separate fresh
   physical proof after stop; pre-stop evidence is never reused.
3. Confirm the current session document is active and the D084 quarantine
   document is a valid active incident. The stopped state inventory is
   recorded and checked again before restart. Missing, corrupt, changed or
   retired documents block recovery.
4. Use the verified D090 journal, exact backup inventory, current source
   profile and proof-collector SHA. Do not alter the 900 s lease, firmware,
   R16/OVP/OCP, `.env`, service unit, or deployment/release authorization.

Run the existing D090 owner from node104 with its already reviewed profile and
collector paths (substitute the exact installed paths and profile SHA):

```bash
sudo /opt/services/rd6018-bot/venv/bin/python \
  /opt/services/rd6018-bot/tools/node104_d090_transaction.py recover \
  --python-release-profile /opt/services/rd6018-bot/d090/<reviewed-profile>.json \
  --proof-collector /opt/services/rd6018-bot/d090/node104_d091_physical_proof_collector.py
```

The D090 owner stops the existing service only after stable pre-stop identity
and fresh physical proof pass, requires another fresh Native proof while
stopped, verifies the complete backup and current-state snapshot, restores only
the old app and virtualenv, then obtains a fresh post-start proof and positive
service stability. A pre-stop refusal leaves service lifecycle untouched.
Failures after stopping leave the service stopped; a failed post-start proof or
stability check requires operator review of the current service and journal.
Do not invoke recovery repeatedly to work around a failed gate; diagnose the
recorded condition and obtain new live proof before a deliberate retry. This
procedure does not clear D084 or resume the session. The restored process must
remain fail-closed under the preserved quarantine.

This repository-side worker performs no node104 file or service operation.
The live ESP proof, service stop/start, and recovery are exclusively for the
existing authorized owner after this source change has been reviewed and
deployed through its normal D090 process.

## Install requested revision

For the requested revision:

```bash
git fetch origin
# checkout/reset only after local operational files are protected
git checkout --detach <requested-sha>
git reset --hard <requested-sha>
```

Verify:

```bash
git rev-parse HEAD
```

The result must exactly equal the requested SHA.

## Dependencies

Use the Python environment already used by the service. Do not silently create a second unrelated environment if the node already has one.

```bash
python -m pip install -r requirements.txt
```

## Mandatory preflight tests

Run before restarting the service:

```bash
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
```

If either command fails:

1. do not start the new revision;
2. keep or restore the previous working deployment;
3. report the failing test/error exactly;
4. do not modify charging code during a deployment-only task unless explicitly authorized.

## Environment flags

Normal production deployment must not inject retired rollback flags.

Normal:

```text
RD6018_EDGE_LEASE_REQUIRED unset/true
```

`RD6018_EDGE_LEASE_REQUIRED=0` exists only as an explicit emergency rollback of the new independent communication-loss boundary. It must not be the normal production configuration and must not be silently introduced to make a failed lease preflight pass.

Rollback policy during modular V3 migration:

- `V2_AUTHORITATIVE=0` is retired and must not be used to re-enable legacy Main/Mix authority.
- UI compatibility flags are not an accepted method of restoring a previous execution owner.
- Control/strategy rollback is an explicit deployment of a known-good commit after normal physical safety prechecks.

For systemd, use the existing unit/environment mechanism; do not invent permanent overrides that resurrect retired owners.

## Restart

Use the existing service manager. For systemd:

```bash
systemctl stop <service-name>
systemctl start <service-name>
systemctl status <service-name> --no-pager
journalctl -u <service-name> -n 150 --no-pager
```

Check that:

- service stays `active (running)`;
- no import/traceback/config/database migration errors appear;
- Telegram polling starts normally;
- Home Assistant connection does not show repeated authentication/entity errors;
- lease entities remain readable and direct Modbus age is fresh;
- no unexpected RD6018 output enable occurs at startup.

## Non-actuating smoke-test boundary

Initial deployment validation must be non-actuating.

Allowed:

- import/startup checks;
- Telegram `/start` / dashboard navigation;
- V2 program preview without confirming a real charge;
- battery registry/list screens;
- Home Assistant entity reads;
- lease entity reads while RD6018 is OFF;
- log inspection.

Not allowed as an initial deployment smoke test:

- pressing Start on a charging program;
- manually turning RD6018 output ON;
- changing voltage/current/OVP/OCP merely to test connectivity;
- running a recovery/HV stage on a battery.

A physical charge is a separate controlled hardware-validation step.

## Controlled edge-failsafe hardware validation

After non-actuating deployment passes, validate the dead-man path on a current-limited dummy load or other low-consequence load before any battery Mix/HV test.

For this validation only, it is reasonable to temporarily use a much shorter edge TTL (for example 90 s with a 20--30 s renewal interval), provided bot and ESPHome configuration use the same test geometry and the production 900 s / 300 s values are restored afterwards.

Prove each of these independently:

1. Normal start: lease generation changes before physical Output ON.
2. Normal running: generation/remaining refresh at the expected cadence.
3. Kill only the Python bot: no renewals occur; ESPHome locally turns RD6018 Output OFF at lease expiry.
4. Stop HA / break the API path: same local OFF occurs without a Python/HA command.
5. Restore communications after expiry: the tripped lease is latched and the old charge does not automatically resume.
6. Verify a fresh controlled start is required after the previous output is confirmed OFF and the lease is disarmed.
7. Temporarily break ESPHome<->RD6018 Modbus: the lease trips and repeatedly requests OFF; once Modbus returns, the first successful local opportunity must result in OFF. Record explicitly that RD6018 may remain energized while the physical UART/Modbus path itself is unavailable.
8. Reboot the ESPHome node during a managed low-power test and verify its persisted managed-session state causes fail-closed OFF rather than resuming the old output.
9. Restore production TTL/cadence and repeat one normal start/stop cycle.

Do **not** make a real 16.3--16.5 V Mix session the first proof of this safety mechanism.

## Native RD6018 Timer Off

The UniSoft firmware has a Current Session `Timer Mode` / `Timer Off` mechanism that can turn Output OFF inside RD6018 itself. This is the desired third layer because it can still operate if the external ESPHome-to-RD6018 UART path is lost.

It is not enabled by this deployment yet. The firmware documentation warns that changing Timer Mode while Output is already ON may produce unexpected behavior, and the currently used public standard RD60xx Modbus map does not identify verified remote addresses/semantics for these Current Session timer fields.

Do not guess, brute-force or write unknown timer registers on an energized battery charger. Follow the bench procedure in `docs/RD6018_FAILSAFE.md`; only after address/readback/reset behavior is proved on the physical RD6018 should native timer renewal become a mandatory backend.

## Runtime files that must survive deployment

Treat these as node data, not disposable source files:

- `.env` and service environment overrides;
- SQLite database(s), including recovery/battery history;
- active session state JSON;
- manual-off state;
- any local logs/history relied on operationally.

Do not replace these with repository defaults.

## Rollback procedure

If startup validation fails:

1. stop the failed service;
2. restore the previous deployed SHA/tree or backup;
3. restore the previous environment flags;
4. start the previous version;
5. verify service state and logs;
6. report both failed and restored SHAs.

Restore an approved previous revision using the documented rollback transaction; historical UI/authority flags are not an execution rollback. Do not remove the edge lease to hide a charging-safety failure.

## Expected deployment report

Return only operational facts:

```text
Deployment: PASS/FAIL
Installed SHA: <sha>
Service: <name> — <active/inactive/failed>
Compile: PASS/FAIL
Tests: <count> PASS / failures
ESPHome lease package: compiled/flashed/not installed
Lease entities: PASS/FAIL
Direct Modbus freshness: <age/status>
Edge failsafe hardware test: PASS/FAIL/not run
Execution authority: canonical modular runtime
RD6018_EDGE_LEASE_REQUIRED: enabled/disabled
Startup logs: <important warnings/errors or none>
Rollback: <previous SHA / backup path / command>
```

Never include tokens or Home Assistant credentials.
