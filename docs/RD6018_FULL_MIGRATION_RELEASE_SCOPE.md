# RD6018 Full Migration Release Scope

Status: `BLOCKED_WITH_REASONS`

Release branch: `v3-full-migration-release`

Base: `ef2b4806a16723eaff67451667d0a2c73fca8fc4`

Release head: `61be65388a273dd12223322bbe0e3df8468e11d2`

Commit range: 272 commits

Changed files: 630 (578 added, 52 modified)

## Scope classification

### A — required architecture migration

Retain for a deliberate full migration review:

- V3 domain/control-plane contracts;
- identity, lifecycle and canonical event models;
- ExecutionIntent and ExecutionPort;
- manual phase/execution boundary;
- safety, ownership and lease changes only where their dependency is proven;
- the V2 physical owner and its verification boundary.

### B — required validation

- focused boundary and ownership tests;
- CI compatibility tests;
- compile/test fixtures required by retained modules;
- migration maps, architecture contracts and source-of-truth documentation.

### C — unrelated or not merge-ready

- accumulated shadow/canary/operator experiments;
- duplicate runtime composition layers;
- `runtime/output/**` write-capable executor surfaces;
- `runtime/physical/**` write-capable connectors/transports;
- physical test/autonomous tooling;
- broad generated/temporary or obsolete migration documentation;
- physical/safety/configuration variants not required by the selected release slice.

No files were removed automatically: the ownership and dependency boundaries are
not yet proven well enough to delete these surfaces safely.

## Required boundary resolution

### Runtime output/physical ownership

The branch still contains `PhysicalBridgeExecutor`, output command plans and
HA/ESPHome/Modbus-capable physical connectors. They must either be removed from
the release or reduced to explicitly read-only/verification contracts. They
cannot remain as a second execution owner beside V2.

### Direct hardware paths

The canonical WS124 `ExecutionPort` path is present, but the branch also retains
many direct V2 `hass.set_voltage`, `hass.set_current`, `hass.turn_on` and
`hass.turn_off` calls in `runtime/v2_runtime.py`, `runtime/v2_lifecycle.py` and
`runtime/v2_startup_recovery.py`. These are the existing V2 owner paths and
must be explicitly classified and protected; they must not be confused with a
new V3 executor.

`manual_mode.py` uses the ExecutionPort boundary for its migrated manual paths.
The broader branch still needs a complete static reachability proof that no
other manual/operator path bypasses that boundary.

### Safety and lease

The branch changes `edge_safety_lease.py`, `runtime/physical/lease/**`,
`runtime/safety/**`, ownership-transition modules and physical/safety configs.
900-second managed lease semantics, local/autonomous behavior and emergency
containment require a focused acceptance review before merge.

## Validation

- CI matrix for the migration head: Python 3.10, 3.11 and 3.12 PASS;
- CI unit-test count: 1714 tests per matrix job;
- CI compile step: PASS;
- release-range `git diff --check`: FAIL due to widespread trailing whitespace
  and blank lines at EOF;
- local compileall: PASS;
- local full test attempt: stopped by an OpenBLAS memory-allocation failure;
  no test or safety behavior was weakened to bypass it.

## Retained / removed / remaining

### Retained

The release branch currently retains the complete migration history so that
dependencies are not silently lost. ExecutionPort and its focused tests are
present.

### Removed

None. Automatic removal would risk deleting required contracts or changing
physical ownership without a reviewed dependency map.

### Remaining blockers

1. Reduce the 630-file branch to a reviewed release scope.
2. Remove or quarantine all secondary write-capable output/physical surfaces.
3. Complete direct hardware reachability and single-owner proof.
4. Resolve safety/lease/configuration scope and acceptance evidence.
5. Clean the release diff so `git diff --check` passes.
6. Re-run the full test matrix after scope reduction.

No merge, deployment, service restart or hardware action was performed.
