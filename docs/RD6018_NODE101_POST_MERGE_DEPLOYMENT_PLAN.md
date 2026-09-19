# RD6018 Node101 Post-Merge Deployment Plan

Status: `BLOCKED_WITH_REASON`

## Merge gate

PR #27 is not approved for merge in the current form. Its diff from `main`
contains 626 changed files and approximately 46,801 additions / 4,536
deletions, including runtime, UI, configuration, physical transport, tests,
and documentation changes beyond the validated WS113B boundary and the
Python 3.11 compatibility fix. No merge was performed.

Validated commits requested for the narrow change:

- `0ff28882de672dd91c041aeb9e591ffe2250389e`
- `0d3db4c4af5ff765753f482f8200691a3efd14b5`

## Node101 current state

- Host: node101 (`192.168.1.101`)
- Service: `rd6018-bot.service`
- Service state: active/running
- Working directory: `/root/rd6018_bot`
- Interpreter: `/opt/rd6018-bot-venv/bin/python`
- Python: `3.11.11`
- Current deployed HEAD: `10af870f7d3ac69ed948ca023318f61827aefa33`
- Local deployed-tree change: `config/charge/manual.yaml` modified
- Current service entrypoint: `/root/rd6018_bot/bot.py`

No service restart or runtime mutation was performed.

## Required deployment steps after scope correction

1. Reduce PR #27 to the explicitly reviewed WS113B changes plus the CI fix.
2. Re-run the complete CI matrix and review the exact resulting merge diff.
3. Record the corrected main merge SHA as the deployment target.
4. Back up `/root/rd6018_bot`, including `.env`, the modified manual config,
   session JSON/SQLite state, and service overrides.
5. Preserve `rd6018-bot.service` and its existing virtual environment.
6. Install dependencies and run `compileall` plus the complete unittest suite
   in the selected Python 3.10+ environment before restart.
7. Only after those checks pass, schedule a separately authorized restart.

## Rollback

Before any deployment mutation, retain the current tree and deployed SHA
`10af870f7d3ac69ed948ca023318f61827aefa33`. On validation failure, restore
the backed-up tree/configuration and keep the existing service/runtime. Do not
discard the local `config/charge/manual.yaml` change.

## Prohibited until unblock

- deployment or service restart;
- START/STOP or setpoint changes;
- lease or ownership changes;
- physical commands.
