# D108 — D090 recovery and temporary OFF-only socket lifecycle (2026-10-18)

## Authority and invariant

This is a continuation of D107 in `timspb/rd6018_bot`, not a new
physical controller or parallel bot. Production node104 remains the
accepted unchanged `8b75cca153f00847d84396aba392472bb7552ad4`.

One ESP128 exists with two routes: Native API **authoritative** for
physical OFF/lease evidence and HA REST **advisory**. A stale HA cache
cannot veto sound Native evidence or substitute for missing Native data.
The 900-second ESP dead-man lease stays unchanged. No changes to battery
recipes, no AGM/MIX retune, and no Output command were made.

## Standard D090 recovery: partial pre-backup directory

Before D108, the standard D090 `recover()` accepted a pre-durable
`PREPARED`/`STOPPED` branch only when no backup directory existed.
A crash after creating an incomplete backup directory but before
journaling `BACKUP_DURABLE` could prevent verified recovery even though
the original app/venv/state/env/marker remained fully intact.

Recovery now rejects symlinks and non-directories, ignores the unsealed
backup **as recovery material**, and verifies the exact live original
baseline and fresh Native OFF proof before any old-service restart.
If the original preimage or observer fails, it remains stopped.
A completed `ROLLED_BACK` entry records
`rollback_without_backup=true` and
`ignored_unsealed_backup=true` when appropriate, with repeat recovery
remaining idempotent. A durable journal phase and damaged durable backup
still fail closed.

## Candidate-only socket ownership

New isolated module `tools/node104_d108_socket_lease.py` owns only:
- the exact temporary systemd drop-in
  `/etc/systemd/system/rd6018-bot.service.d/90-d090-off-only-trial.conf`;
- the canonical AF_UNIX socket
  `/run/rd6018-bot-physical-test-control.sock` (only when candidate
  process is confirmed stopped).

Opt-in is restricted to:
`RD6018_PHYSICAL_TEST_CONTROL=1` and the exact socket path.
Drop-in is exclusive-create, mode 0600; pre-existing files, other
systemd overrides, non-owned/malformed/symlink paths fail closed.
Cleanup checks exact drop-in bytes, permissions and ownership.
An unconnected stale root-only socket inode may be removed; a still-live
listening socket is never unlinked. Unexpected overrides appearing while the
trial runs stop cleanup before the old bot can start; the foreign file is
never removed. Cleanup runs `daemon-reload` again if a previous crash
happened after deleting the drop-in.

The old `SystemdService.layout_valid` used a substring test for
`DropInPaths=` that would also accept `DropInPaths=/unwanted/override`.
D108 parses the systemctl show properties exactly. Normal production
requires empty `DropInPaths`; trial stability permits only the exact
D108 drop-in path and verifies root ownership, strict mode 0600, and
exact reviewed file bytes. The trial-candidate stability check calls
`layout_valid(trial=True)`; standard release admission uses the
default strictly empty override set.

D090 `begin_trial()` invokes optional socket-install hook after
candidate swap and before candidate start. Locked D090 trial recovery
invokes the matched cleanup hook before old service restart, not via a
separate release owner. A failure between socket installation and
candidate start is covered. If the original bot was never stopped
(`PREPARED`), no socket mutation is allowed. The socket can never
serve as physical OFF proof; D091+Native gates remain mandatory.

`node104_d106_readonly_socket.py` additionally requires
`set_current <= OCP` and an exact integer zero count of injected
RD actuator writes in the status receipt. Its status query remains
read-only and verifies the root-owned 0600 AF_UNIX socket and
matching production peer PID/UID.

## Verification

In an isolated WSL2 Ubuntu-24.04 worktree, test groups:
`test_node104_d108_socket_lease`,
`test_node104_d105_trial_lifecycle`,
`test_node104_d090_transaction`,
`test_node104_d106_socket_status`,
`test_node104_d106_readonly_recovery`,
`test_node104_d091_physical_proof_collector`
completed **122/122 PASS**. A later expanded D090–D108\nregression matrix completed **158/158 PASS**, and focused\npost-hardening D090/D105/D106/D108 completed **108/108 PASS**.\nThe final combined D090/D091/D094/D102/D105/D106/D107/D108 suite\ncompleted **161/161 PASS** on WSL2. The final source tree also passed\n`compileall -q` and `git diff --check` against D106 main.

This includes explicit pre-durable partial backup/tamper/symlink
failure injection, crash before stop, after socket installation,
drop-in deletion before reload, malicious socket path, live listener,
permissions and retryable recovery. Existing D107 native proof
regressions are preserved.

The broader bare WSL2 `unittest discover` started successfully:
**2,109 tests; 18 import errors; 2 skipped**. All 18 known errors
arose because the isolated worker lacked `TG_TOKEN` at
`runtime.production_runtime` import, not from the D108 test group.
No full-suite PASS is claimed. GitHub CI for D107/D108 is not confirmed.

## Remaining boundaries

**Production release/physical trial still BLOCKED, not silently promoted**:
1. D090 production `_trial_gate` deliberately rejects live trials and
   does not wire the temporary socket lease. The new socket module has
   only fake-root/offline tests; no live drop-in was created.
2. The existing production D090 CLI collector SHA still pins
   `c6bf8f456c06da75816976946a9129ccd7619237b6e482874c25a4aa9951ace8`,
   whereas the reviewed D107/D108 branch file
   `tools/node104_d091_physical_proof_collector.py` now hashes to
   `adad502b02f48327a08922a4ae08030b990a222680825e6b56d92ef0b6f5742e`.
   The source-only D106 observer SHA is
   `482c8ff747377f5043096cd14473279138053bbf235f22d415836615e73178c2`;
   temporary socket helper SHA is
   `7ffe063c8430f771e58ee5eed75735489d596f487e1888ed153dee70e9c19ddf`.
   These are verified file hashes, **not** production deployment pins.
   D090 CLI must not be invoked with a mismatched collector; bind it
   only after live Native read-only acceptance of the exact new file.
3. D103/D105 trial candidate and socket-enabled composition must be
   independently verified together against their immutable source pins.
4. Fresh Native preflight must be repeated at any prospective physical
   activation boundary. OFF-only trial and D097 Enter/Exit have not run.
5. Restore proof must include absence of temporary drop-ins/socket,
   original exact app+env+venv+state/unit/marker, one stable old
   production owner and no unwanted actuator write.

Do not call these source-only tests production acceptance. No
`systemctl stop/start`, drop-in install, lease operation, Output
ON/OFF or D097 physical actuation has been executed.
