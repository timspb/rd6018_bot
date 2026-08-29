# Deployment and rollback runbook

This document is for replacing the bot on an existing node. It intentionally does not prescribe a new service layout: discover and preserve the node's current runtime, virtualenv and service manager.

## Production model

Normal V2 production launch:

```bash
python bot.py
```

`bot.py` is a small V2 entrypoint. The previous large runtime is preserved as `bot_legacy.py` and is imported/wrapped by the V2 bootstrap.

Production controller:

```text
ProductionChargeControllerV2
  -> ChargeControllerV2 authority for non-Custom Main/Mix
  -> legacy safety/mechanics scaffold
  -> recipe envelope
  -> SafeOutputCoordinator / HassClient
  -> RD6018 via Home Assistant
```

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
- writable runtime files/database location.

Do not print secrets into reports.

## Backup

Before modifying the working tree, preserve a quick rollback target. At minimum record the deployed SHA:

```bash
git rev-parse HEAD
git status --short
```

If the deployed tree contains local operational files or uncommitted configuration, back up the complete directory or the relevant local files before checkout/reset. Do not discard local `.env`, SQLite databases, session JSON or service overrides.

## Install requested revision

For this V2 branch:

```bash
git fetch origin
# checkout/reset only after local operational files are protected
git checkout refactor/pb-recovery-controller-v2
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

Normal V2 deployment must not inject rollback flags.

Normal:

```text
V2_UI unset/true
V2_AUTHORITATIVE unset/true
```

Rollback options:

```bash
# Old UI only
V2_UI=0 python bot.py

# Legacy Main/Mix authority, V2 UI remains
V2_AUTHORITATIVE=0 python bot.py

# Full rollback through current entrypoint
V2_UI=0 V2_AUTHORITATIVE=0 python bot.py

# Preserved old runtime directly
V2_AUTHORITATIVE=0 python bot_legacy.py
```

For systemd, use the existing unit/environment mechanism; do not invent permanent overrides unless rollback is intentionally being activated.

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
- no unexpected RD6018 output enable occurs at startup.

## Smoke-test boundary

Deployment validation must be non-actuating.

Allowed:

- import/startup checks;
- Telegram `/start` / dashboard navigation;
- V2 program preview without confirming a real charge;
- battery registry/list screens;
- Home Assistant entity reads;
- log inspection.

Not allowed as a deployment smoke test:

- pressing Start on a charging program;
- manually turning RD6018 output ON;
- changing voltage/current/OVP/OCP merely to test connectivity;
- running a recovery/HV stage on a battery.

A physical charge is a separate controlled hardware-validation step.

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

If code rollback is unnecessary and only V2 presentation/authority must be disabled, use the rollback flags above first.

## Expected deployment report

Return only operational facts:

```text
Deployment: PASS/FAIL
Installed SHA: <sha>
Service: <name> — <active/inactive/failed>
Compile: PASS/FAIL
Tests: <count> PASS / failures
Startup logs: <important warnings/errors or none>
V2_UI: enabled/disabled
V2_AUTHORITATIVE: enabled/disabled
Rollback: <previous SHA / backup path / command>
```

Never include tokens or Home Assistant credentials.
