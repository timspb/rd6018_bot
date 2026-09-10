# Node 101 rebaseline execution checklist

Operator checklist for a controlled rebaseline of production node 101. This
document is executable only during an approved maintenance window. It is not
authorization to connect to the host, stop services or delete files.

## Scope and current baseline

- Node: `192.168.1.101`
- Service: `rd6018-bot.service`
- Current production SHA: `613f1521...`
- Current condition: active service, dirty checkout, eight modified runtime
  files, `.env`, database, session state and rollback artifacts present
- Application scope: `/root/rd6018_bot`

Do not clean the whole host. Preserve system services, network services,
ESPHome/firmware, hardware state and all files listed under KEEP below.

## 1. Safety gate

Complete before any mutation and record the source plus timestamp for every
item.

- [ ] Output state captured from direct RD/edge readback: `__________`
- [ ] Current service state captured: `__________`
- [ ] Current PID captured: `__________`
- [ ] Current deployed SHA captured: `__________`
- [ ] Current stage/mode/session captured: `__________`
- [ ] Backup destination exists and has sufficient space: `__________`
- [ ] Rollback path was tested/readable: `__________`
- [ ] No active charge or unsafe HV operation: `__________`
- [ ] Maintenance window and operator approval recorded: `__________`

Do not continue if Output, ownership, session or rollback state is ambiguous.

## 2. Backup gate

Create and verify a timestamped backup before stopping the service. Record the
absolute path, size and checksum where applicable.

- [ ] Full `/root/rd6018_bot` application tree backup: `__________`
- [ ] `.env` backup: `__________`
- [ ] `rd6018.db` backup: `__________`
- [ ] `charge_session.json` backup: `__________`
- [ ] All runtime JSON/state files backup: `__________`
- [ ] `rd6018-bot.service` unit backup: `__________`
- [ ] Service overrides/environment files backup: `__________`
- [ ] Venv path, interpreter and package information recorded: `__________`
- [ ] Current `git diff` export for eight modified runtime files: `__________`
- [ ] Untracked/rollback/artifact inventory recorded: `__________`
- [ ] Backup restore/readability check passed: `__________`

### Files to keep in place

Do not replace or delete these during repository restore:

- `.env` and credentials;
- `rd6018.db`;
- `charge_session.json` and runtime state JSON;
- hardware identity and local operational configuration;
- systemd unit and service overrides;
- the supported active venv until the replacement is validated.

## 3. Clean restore

Perform only after sections 1–2 are complete.

- [ ] Stop `rd6018-bot.service` using the existing service manager.
- [ ] Confirm no `bot.py`/`bot_legacy.py` process remains.
- [ ] Confirm no process has an open write handle to `rd6018.db`.
- [ ] Confirm RD Output remains OFF and no actuator command was issued.
- [ ] Preserve the dirty checkout; do not discard it before backup verification.
- [ ] Restore repository-managed files to the approved exact SHA: `__________`
- [ ] Restore preserved `.env` and credentials without printing secrets.
- [ ] Restore database and session/runtime state without editing contents.
- [ ] Remove only approved generated artifacts and obsolete deployment leftovers.
- [ ] Verify file owner, group and permissions against the preflight record.
- [ ] Verify the original service `ExecStart`, working directory and venv path.
- [ ] Verify dependencies in the selected Python 3.10+ environment.

Do not use a broad host-wide delete, `git reset --hard` without the verified
backup, or repository defaults for production data/configuration.

## 4. Startup validation

### Before starting the service

- [ ] `python -m compileall -q .` — result: `__________`
- [ ] `python -m unittest discover -s tests -p 'test_*.py'` — result: `__________`
- [ ] Service unit syntax/configuration verified: `__________`
- [ ] `.env` present and permissions verified: `__________`
- [ ] Database backup and SQLite integrity verified: `__________`
- [ ] Session/runtime JSON is present and unchanged: `__________`
- [ ] No startup path can issue an unexpected actuator command: `__________`

If compile, tests, dependencies or configuration fail, do not start the new
runtime; follow rollback.

### After starting the service

- [ ] Service is `active/running`: `__________`
- [ ] New PID: `__________`
- [ ] Exactly one production `bot.py` process: `__________`
- [ ] Telegram polling is healthy: `__________`
- [ ] No import, traceback, authentication or migration errors: `__________`
- [ ] SQLite integrity is OK: `__________`
- [ ] Session/stage/mode are as expected: `__________`
- [ ] Output remains safely OFF: `__________`
- [ ] No unexpected automatic restore or actuator command: `__________`
- [ ] Rollback backup remains readable: `__________`

Record log window and evidence archive: `__________`

## 5. AUTONOMOUS separation

This node 101 rebaseline does **not** include:

- AUTONOMOUS deployment;
- ESPHome flashing or firmware changes;
- physical AUTONOMOUS validation;
- production rollout of new AUTONOMOUS behavior;
- new authority paths or safety changes.

The rebaseline must leave the existing production authority and safety
contract unchanged. Physical validation uses the frozen evidence workflow
after a separately approved bench deployment.

## 6. Rollback

Stop the new runtime and roll back immediately if any trigger occurs:

- service fails to start or remains unhealthy;
- compile/test/dependency validation fails;
- database integrity or accessibility fails;
- session/runtime state is missing or unexpectedly changed;
- a secret, credential or required configuration is missing;
- an unexpected startup actuator command occurs;
- Output changes unexpectedly or ownership is ambiguous;
- Telegram polling or HA connectivity is broken beyond the approved baseline;
- permissions, venv or service definition differ unexpectedly.

Rollback steps:

1. Stop the failed service.
2. Confirm no replacement process remains and Output is safe.
3. Restore the backed-up application tree and preserved operational files.
4. Restore the original service environment/unit if changed.
5. Start the recorded previous deployment SHA.
6. Verify service, PID, one bot process, polling, database and Output state.
7. Record failed SHA, restored SHA, timestamps and evidence.

Rollback result: `PASS / FAIL / NOT USED`

## Closeout

- Approved exact SHA installed: `__________`
- Production SHA after operation: `__________`
- Service/PID: `__________`
- Output state: `__________`
- Database/session state unchanged: `YES / NO`
- Operator: `__________`
- Reviewer: `__________`
- Evidence archive: `__________`
