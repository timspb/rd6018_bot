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

## Offline candidate trial

The existing tools/node104_atomic_deploy.py stage command produced a verified
local candidate from exact HEAD 82659d5, under
/tmp/rd6018-release-candidate-20261104 on HOME-PC WSL only (not on node104).
Its complete source.tar is about 9 MB, with a 251 KB release manifest.
The stage constructor checked archive digest and all unpacked source hashes.

Full pytest inside the source-only archive gave 2842 passed, 9 skipped,
1 failed, 1658 subtests passed. The lone failure was an old D123 test
calling git rev-parse from inside an archive that intentionally lacks .git.
The D123 VCS-only fixture has now been correctly scoped with skipUnless to
a Git checkout, while still running in CI/source worktrees. The five
other D123 source-release tests pass in the Git worktree (5 passed).
This is a test-environment contract adjustment, not a bypass of charger
behavior. Re-stage and re-test from the next committed source HEAD.

Do not infer a production deployment from this offline candidate.

## Verified release candidate fa60c16

The second candidate was staged by the existing offline
tools/node104_atomic_deploy.py from exact commit fa60c16 under
/tmp/rd6018-release-candidate-20261104/release-fa60c16cc4bf3420d29bf0cfad184d9572e6182f-iv_je3jp.
The staging operation verified the source.tar digest and its complete
unpacked file SHA256 manifest.

Entire pytest suite inside the unpacked **source-only** candidate:
**2842 PASS, 10 SKIPPED, 5 WARNINGS, 1658 subtests PASS, 0 failures and
0 errors** in 138.71 seconds. Evidence:
HOME-PC WSL /tmp/rd6018-candidate-fa60c16-full.log.
VCS-dependent tests properly skip in source-only releases; D123 tests pass
in the local source checkout.

The successful offline candidate is not a deployed or activated release.
No remote service restart, database write, hardware output, or state
migration took place. The node104 live baseline must be rechecked before
any installation or switch-over.
