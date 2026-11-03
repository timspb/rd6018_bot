# RD6018 node104 — reconciled deployment plan (2026-11-04)

This is a read-only preparation plan, **not permission to activate or interrupt a charge**.

## Evidence and installed architecture

Source commit: 91c72df25b60a9435ad066385b9a4e5e39ecdedb. Full 59-file source
comparison with verified remote SHA256 is in RD6018_NODE104_DEPLOY_DELTA_2026-11-04.json.
13 source files match byte for byte, 40 differ, and 6 are absent on node104.

The systemd service executes /opt/services/rd6018-bot/venv/bin/python
/opt/services/rd6018-bot/app/bot.py as user rd6018. Working directory is
/opt/services/rd6018-bot/state. Code is root-owned; state is writable by
rd6018. The persistent DB rd6018.db, user_recipes directory, recovery
quarantine, and MIX-authority file are present. No active charge_session.json
was found at the checked app/state paths, but external charging under
hands_off is still possible. Systemd service active PID 196930, no restarts;
persisted control mode hands_off. Last read-only clock 2026-11-03 14:22 UTC.

The local migration affects bot initialization, operator and Telegram UI,
database interfaces, controller targets, MAIN/MIX/DESULFATION/SAFE_WAIT owners,
session restore, and recipe versions. Do **not** install only six missing files
or just the Telegram UI. This inventory is the difference from Git origin/main,
NOT a complete dependency-closed release manifest.

## Candidate preparation

1. Re-read the existing node104 deployment/release scripts. Build the candidate
   from the **complete exact tested Git source**, not from incremental patches.
   Include a normalized full-file SHA256 manifest and dependency/import checks.
2. Run the complete regression suite on the exact candidate in an isolated
   checkout. Earlier c637922 source baseline passed 2849 tests, 1666 subtests
   with 3 skipped; later commits 3cd4ead and 91c72df changed documentation.
3. Check Telegram catalog, button callbacks, graphs, hands_off display, recipe
   state persistence, and restart restore with fake hardware, no external
   polling token and no second charging owner.
4. Exclude and preserve outside the candidate: .env, secrets, venv,
   /opt/services/rd6018-bot/state, logs, backups, rd6018.db, user_recipes,
   control mode and all operational state. Respect existing systemd unit.
5. Compare expected live file hashes and service state again immediately
   before activation; re-evaluate drift rather than force overwrite.
6. Store one coherent recoverable prior source release and its manifest.
   Avoid recursive backups and uncontrolled cyclical rollback.
7. Activate only when physical charge/ownership is understood and service
   interruption is safe. Restarting the Telegram service is NOT safe to assume
   during a live externally controlled charge.
8. Verify exactly one polling owner, hands_off unchanged, DB and graphs intact,
   versioned native copies and original recipes usable. No physical START/OFF
   or setpoint action without explicit operational control transfer.

## Disposition

Candidate not installed. node104 not modified, service not restarted,
physical charging not touched. A local untracked
charge_session.json.mix-authority.json is test-produced, not part of release;
do not delete it while an old test owns it. Do not push into foreign upstreams.

Next: locate and validate the existing release installer, generate a complete
source manifest, and test in isolation before a controlled deployment window.
