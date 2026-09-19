# RD6018 Full Migration PR Audit

Status: `BLOCKED_WITH_REASONS`

## Scope under review

- Base (`main`): `ef2b4806a16723eaff67451667d0a2c73fca8fc4`
- PR #27 HEAD: `c4baca2daef0b13baf8aa4a330c1cadd92856988`
- Commits in PR: 272
- Changed files: 626
- Approximate diff: 46,801 additions / 4,536 deletions

## Decision

PR #27 is not a merge-ready narrow WS113B release. It is an accumulated V3
migration tree and must be reviewed as a release-sized change. It is not safe
to merge under the assumption that it contains only the validated manual phase
boundary and the Python compatibility fix.

## Architecture findings

### Confirmed boundaries

- `ManualPhaseLifecycle` produces phase decisions and `ExecutionIntent`.
- `ManualExecutionBoundary` receives the decision and performs readback-aware
  execution through the injected V2 owner.
- Identity and canonical event contracts are present.
- The production entrypoint still starts `runtime.v2_runtime`, so V2 remains
  the apparent production controller in the inspected path.

### Boundary risks requiring explicit acceptance or removal

- `manual_mode.py` still owns direct physical `turn_off()` calls on stop and
  exception paths. The MAIN-to-MIX setpoint path uses the new boundary, but the
  manual physical ownership boundary is not completely isolated.
- The PR adds a substantial `runtime/output` and `runtime/physical` tree,
  including executors, HA/ESPHome connectors, leases, and bench transitions.
  This creates a second physical execution surface that must be proven
  non-production and non-authoritative before merge.
- `bot.py` changes production composition and `bot_legacy.py` is reduced by
  thousands of lines. This exceeds a local WS113B boundary change and affects
  rollback provenance.
- Lease, safety, identity, audit, and operator changes are distributed across
  a broad migration rather than one independently reviewable release unit.

## Scope classification

### A — required for the manual boundary migration

- `manual_mode.py` boundary call-site changes;
- `application/manual_phase_lifecycle.py`;
- `application/manual_execution_boundary.py`;
- `application/manual_identity_integration.py`;
- `application/v2_identity_bridge.py` and execution-intent contracts;
- canonical event/identity tests and the WS113B migration documentation.

### B — supporting migration material

- focused boundary, identity, audit, lifecycle, telemetry, UI and parity
  tests;
- canonical V3 domain models and their documentation;
- read-only operator/shadow evidence components;
- CI dependency metadata required by the validated matrix.

These files may belong to a full migration release, but they require a
separate release-level review rather than being implicitly accepted as part
of WS113B.

### C — remove, split, or explicitly approve before merge

- broad production entrypoint/runtime rewrites;
- `bot_legacy.py` large deletion and rollback-surface changes;
- `runtime/physical/**` connectors and transports;
- `runtime/output/**` physical executor and controlled transition paths;
- `config/physical/**` and bench execution configuration;
- autonomous physical validation tooling;
- unrelated UI, canary, deployment, and accumulated migration commits;
- whitespace/newline noise and generated-looking artifacts failing diff
  hygiene.

## Regression and contamination review

- No obvious private-key or token pattern was found in the reviewed diff
  search, but the scope is too broad to treat this as a substitute for a
  formal secret scan.
- Direct HA/ESPHome/Modbus calls exist in the new physical infrastructure
  tree. They are not acceptable inside pure domain modules and must remain
  isolated from the production V3 decision path.
- The presence of `runtime/output/bridge/executor.py` and
  `runtime/physical/connectors/**` is a duplicate-execution-surface risk even
  where current production wiring does not import it directly.
- Existing V2 runtime still contains direct physical calls by design; that is
  compatible with V2 ownership only if the new tree is proven non-authoritative.

## Validation state

- GitHub Actions run `35043436944` for `c4baca2d`: PASS on Python 3.10,
  3.11, and 3.12.
- Local `compileall`: PASS on the available Python 3.14 interpreter.
- Local `git diff --check` against `main`: FAIL; the accumulated diff contains
  trailing whitespace and extra blank lines.
- Full local 3.10/3.11/3.12 reproduction was not available; CI is the matrix
  evidence.

Green CI proves the test matrix for this HEAD, not that the 626-file change
set is an acceptable migration release.

## Node101 compatibility

- Current HEAD: `10af870f7d3ac69ed948ca023318f61827aefa33`
- Service: `rd6018-bot.service`, active/running
- Working directory: `/root/rd6018_bot`
- Interpreter: `/opt/rd6018-bot-venv/bin/python`, Python `3.11.11`
- Local deployed-tree change: `config/charge/manual.yaml`
- Current entrypoint: `/root/rd6018_bot/bot.py`

The node is not aligned to PR HEAD. Deployment was not attempted.

## Required next action

1. Do not merge PR #27 in its current form.
2. Decide whether this is the intended full migration release. If yes, perform
   a dedicated release review for all A/B/C categories and explicitly approve
   the physical infrastructure and production-entrypoint changes.
3. If the target is only WS113B plus the CI fix, produce a reduced branch/PR
   containing only the validated boundary and its required supporting files.
4. Resolve `git diff --check` failures and rerun CI on the final reviewed
   tree.
5. Only then update the node101 deployment plan; do not deploy the current PR.

Final status: `BLOCKED_WITH_REASONS`
