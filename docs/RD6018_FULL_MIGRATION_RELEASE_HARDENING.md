# RD6018 Full Migration Release Hardening

Status: `BLOCKED_WITH_REASONS`

Branch: `v3-full-migration-release`

HEAD: `61be65388a273dd12223322bbe0e3df8468e11d2`

## Before hardening

The branch contains 272 commits and 630 changed files relative to
`ef2b4806a16723eaff67451667d0a2c73fca8fc4`.

Observed ownership surfaces:

- V2 runtime/Hass owner: existing production physical path;
- `application.ExecutionPort`: new canonical WS124 boundary;
- `runtime/output/bridge/PhysicalBridgeExecutor`: independent write-capable
  executor surface;
- `runtime/physical/connectors/**` and `transports/**`: HA/ESPHome-capable
  write connectors;
- `runtime/physical/commands/**`: physical command contracts and verification;
- `physical_test_control_pb_mode.py` and autonomous physical test tooling.

The manual path is migrated through `ExecutionPort`, but the branch still has
many direct V2 owner calls in `runtime/v2_runtime.py`, `runtime/v2_lifecycle.py`
and `runtime/v2_startup_recovery.py`. Those are acceptable only as the single
V2 owner and must not be duplicated by the V3/output/physical surfaces.

## Hardening result

No write-capable surface was deleted or silently rewritten. Safe removal is not
possible without first updating the extensive dependent test and migration
layers. The branch therefore remains functionally unchanged and the blockers
remain explicit:

### Physical/output ownership — BLOCKED

`PhysicalBridgeExecutor` and physical connectors remain present and tested as
independent execution-capable surfaces. They are not reduced to read-only
adapters by this workstream.

### Manual hardware paths — PARTIAL

`manual_mode.py` routes start, stop, cooling, resume and error shutdown through
`ExecutionPort`. A full repository reachability proof is still blocked by the
parallel runtime/output and runtime/physical command trees.

### Safety/lease scope — BLOCKED

The branch includes changes to `edge_safety_lease.py`, `runtime/physical/lease`,
`runtime/safety`, ownership-transition modules and physical/safety configs.
The required 900-second managed-only lease semantics and local/autonomous
independence need a focused acceptance review before merge.

### Diff hygiene — BLOCKED

`git diff --check ef2b4806..HEAD` fails with widespread trailing whitespace and
blank lines at EOF, including `runtime/v2_runtime.py` and many migration docs.
No broad formatting rewrite was applied because it would obscure the release
boundary.

## Validation

- ownership/manual focused tests: previously PASS on the validated WS124 slice;
- CI matrix on the migration head: Python 3.10/3.11/3.12 PASS;
- CI compile step: PASS;
- local compileall: PASS;
- full local test attempt: failed in the environment with an OpenBLAS memory
  allocation error; no tests were weakened or skipped to conceal it;
- release-range diff-check: FAIL.

No node101 deployment, service restart, configuration mutation, merge or
hardware action was performed.

## Required next release actions

1. Choose one physical execution owner and remove/quarantine the other
   write-capable trees with a reviewed dependency migration.
2. Re-run static reachability from production composition and manual/operator
   entrypoints.
3. Review safety/lease changes against the source-of-truth semantics.
4. Clean whitespace in a bounded, reviewable change.
5. Re-run the complete test matrix in a resource-sufficient environment.

Final decision: `BLOCKED_WITH_REASONS`.
