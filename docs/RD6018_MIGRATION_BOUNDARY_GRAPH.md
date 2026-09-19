# RD6018 Migration Boundary Graph

Status: `FULL_MIGRATION_RELEASE_REQUIRED`

Scope: read-only history analysis from `main` (`ef2b4806`) to the current
migration branch head (`61be653`). The range contains 272 commits.

## Dependency graph

```text
main ef2b4806
  |
  +-- accumulated V3/runtime/ownership migration (many unrelated commits)
  |
  +-- b5d05f5  Phase 1 cleanup contracts
  |       |
  |       +--> tests/test_phase1_cleanup_contracts.py
  |
  +-- c2d5125  runtime app/output-enable inventory
  |       |
  |       +--> tests/test_legacy_enable_inventory.py
  |
  +-- 0ff2888  Manual phase lifecycle boundary
  |       |
  |       +--> ManualPhaseLifecycle
  |       +--> ManualSessionIdentity / canonical events
  |       +--> ManualExecutionBoundary
  |       +--> manual_mode consumers
  |       +--> WS113B boundary tests
  |
  +-- 25f2a6a  ExecutionIntent contracts
  |       |
  |       +--> ExecutionIntent / SafetyContext
  |       +--> phase cleanup test extension
  |
  +-- ad3b97f  ExecutionPort consolidation
  |       |
  |       +--> manual start/stop/resume/cooling/error paths
  |       +--> manual_runtime_v2 disable paths
  |       +--> manual execution boundary delegation
  |       +--> ownership/inventory tests
  |
  +-- 61be653  Python 3.11 dataclass compatibility
          |
          +--> charge_event / diagnostics_domain MappingProxy defaults
```

## Consumer relationships

| Producer | Consumer | Required contract |
|---|---|---|
| `ManualIdentityIntegrationAdapter` | `manual_mode.py` | session/trace identity |
| `ManualPhaseLifecycle` | `manual_mode.py` | phase decision and target intent |
| `ExecutionIntent` | `ManualExecutionBoundary`, `ExecutionPort` | approved target envelope |
| `ExecutionPort` | `manual_mode.py`, `manual_runtime_v2.py` | V2-owned execution and verification |
| V2 owner | `ExecutionPort` | guarded enable, setters, verified OFF, readback |
| `v3_core.canonical_events` | manual lifecycle/evidence | canonical event identity |
| `test_phase1_cleanup_contracts.py` | WS124 inventory tests | existing test helper/inventory base |
| `test_legacy_enable_inventory.py` | WS124 inventory update | existing actuator inventory base |

## Smallest coherent candidate

At source level, the minimum functional boundary is:

1. `0ff2888` — identity, lifecycle, boundary and manual integration;
2. `25f2a6a` — the `ExecutionIntent` contract required by the boundary;
3. `ad3b97f` — the single `ExecutionPort`, manual runtime routing and
   ownership tests;
4. the required portions of `b5d05f5` and `c2d5125` if their existing test
   inventories are retained.

`61be653` is not part of the execution boundary itself. It is required only
when the broader V3 `charge_event` and `diagnostics_domain` modules are also
included and imported by the test matrix.

## Why this is not a clean commit slice

The candidate is not standalone as a commit sequence on `main`:

- `main` does not contain `application/manual_execution_boundary.py`;
- `main` does not contain `application/manual_phase_lifecycle.py`;
- `main` does not contain `application/execution_intent/models.py`;
- `main` does not contain the WS113B boundary test;
- `main` does not contain the two inventory test files that later commits
  modify;
- `manual_mode.py` has divergent content and conflicts with the WS113B/WS124
  patch context.

The attempted clean cherry-pick produced modify/delete conflicts for the
boundary and inventory tests and a content conflict in `manual_mode.py`. This
is evidence that the commit graph depends on migration context outside the
two requested commits.

## Classification

### KEEP for a future coherent slice

- WS113B identity/lifecycle/manual boundary contracts from `0ff2888`;
- `ExecutionIntent` contracts from `25f2a6a`;
- `ExecutionPort` and manual routing from `ad3b97f`;
- only the focused ownership/boundary tests needed by those files;
- the matching migration documentation.

### DROP from that slice

- unrelated V3 canary, shadow, operator and evidence layers;
- independent runtime/output and runtime/physical executor/connector trees;
- unrelated physical/safety/lease/configuration migrations;
- broad accumulated documentation and test suites;
- unrelated runtime characterization and deployment artifacts.

### LATER / separate review

- `61be653` dataclass compatibility, unless the selected slice keeps the
  modules that require it;
- lease, safety, ownership-transition and physical-adapter work;
- full V3 runtime and operator migration.

## Decision

`FULL_MIGRATION_RELEASE_REQUIRED`

A coherent boundary can be reconstructed, but not by cherry-picking only
`ad3b97f` and `61be653` onto `main`. The next safe unit must be assembled as a
new, explicitly bounded release commit/branch with the required WS113B and
ExecutionIntent contracts, or the full migration release must be reviewed as
one unit. No commit or merge was created by this analysis.
