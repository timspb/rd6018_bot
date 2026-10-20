# D123 Sprint 53 — production host convergence

Status: source-only continuation from exact clean HEAD
`54f26958d6c4eab332120723a2a84f7048383749` on
`codex/d118-start-lease-repair-20261019`. No node104, ESP, HA, firmware,
service, deployment, GitHub, or physical output was accessed or changed.

## Cut and method counts

AST counts for `ProductionChargeController`:

| Measure | Before (Sprint 52) | After Sprint 53 |
| --- | ---: | ---: |
| Declared methods | 10 | 1 |
| Methods overriding `ManagedChargeController` | 8 | 1 |

The only remaining declaration is `try_restore_session`. The six target
adapters and recipe envelope application now run through the existing base
host and `application.production_target_policy`. Production runtime choice
is selected by `application.production_runtime_policy` from the existing host
factory. Production extension initialization and session-document projection
are owned by `application.production_session_extensions` and canonical
`runtime.charge.session_atomic`; the controller forwarding hook is removed.
All mutable extension state stays on the one charge host.

The remaining restore method calls canonical base restore, retains the
authority-bearing MAIN Guard journal read in its existing order, then calls
`restore_production_session_state` for non-Guard defaults, MIX finish/runtime
signal reconstruction, target bounds, and fail-closed cooling pause validation.
No Guard admission behavior or restore ordering changed. Ordinary raw document
handoff remains canonical and singular.

## Architecture and scope

Static gates assert that production declares only `try_restore_session`, the
moved adapter/hook names stay absent, the production extension module declares
no class/state host, and canonical production composition retains one host.
Session atomic remains the only persistence writer. Extension modules define
no physical writer. Existing target, Guard, START, restore and cooling
regressions exercise the moved behavior.

No recipe/algorithm, 900 s lease, safety, OVP/OCP, ESP-priority, Manual, or
physical path was changed. MAIN Guard restore remains fail-closed/deferred.
No dependencies were installed. The outer runner performed the canonical full-suite validation and commits this validated source-only cut.

## Verification

- Focused target/runtime/session/restore/Guard set: **91 PASS**.
- Python 3.12 discovery of `tests/test_*.py` with synthetic
  `TG_TOKEN=123456789:d123-continuation`: **2,452 tests; 2,445 PASS,
  3 skipped, 4 errors, 0 assertion failures**. A process-local selector poll
  cap allowed discovery to complete after the ordinary invocation stalled.
  The four errors are sandbox socket restrictions: three Unix socket binds
  and one loopback TCP server bind, each `PermissionError: Operation not
  permitted`. Full log: `/tmp/d123-sprint53-full-final.log`.
- `/home/home-pc/rd6018-v3-deploy/.venv/bin/python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

## Exact remaining boundary

P4 inheritance is **not closed**. The sole remaining subclass override is the
P2 ordinary restore/MAIN Guard admission boundary. The method still bridges the
canonical raw restore document and fail-closed Guard journal reconstruction.
Removing the subclass now would move that authority-bearing admission or
duplicate the restore schema/host. P2 Guard admission remains deferred; no
broader restore owner migration is claimed.
