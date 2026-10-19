# D123 Sprint 15 — residual observation mutation owner

Date: 2026-10-19. Exact starting HEAD: `37df3cee3ec187fc330626b107f71c1ec4915a95`.
Source-only workspace change. No node104, ESP, HA, live system, deployment,
service, GitHub, or external system was accessed.

## Bounded ownership cut

The production caller remains `ManagedChargeController._run_stage_scaffold_tick`
through `run_authoritative_residual_scaffold`. Sprint 15 moves one concrete
shared observation mutation behind the existing `runtime.charge.evidence`
boundary: updating latest sample mirrors and appending analytics and throttled
V/I history for residual stages. `residual_observation.record_residual_observation`
uses the canonical `mark_stage_sample` helper and owns the history writes.

Parity is retained: IDLE updates sample mirrors but remains excluded from
analytics and V/I histories; DONE continues to append its analytics sample and
interval-gated V/I samples. The residual scaffold no longer directly invokes
`host._mark_stage_sample` or mutates those histories. Timing corrections,
temperature/link safety, pending-log/report mutation, persistence and stage
decisions remain with their prior owners. Session schema, Guard, lease, recipes,
fail-closed behavior and physical execution routing are unchanged;
`application.execution_port` remains the sole physical writer.

## Changed files

- `runtime/charge/runtime/residual_observation.py` — residual sample/history
  mutation owner.
- `runtime/charge/runtime/residual_scaffold.py` — one call to the observation
  owner; direct sample/history mutations removed.
- `tests/test_d123_p3_residual_terminal.py` — IDLE/DONE observation parity,
  single-call ownership and no-writer guards.
- `docs/architecture/D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` —
  Sprint 15 status and remaining scope.
- `docs/architecture/D123_CONTROLLER_OWNER_MAP_20261019.md` — actual call path,
  mutation ownership and boundaries.

## Focused verification

Command, using `/home/home-pc/rd6018-v3-deploy/.venv/bin/python` and synthetic
`TG_TOKEN=123456789:d123-sprint15`:

```bash
python -m unittest tests.test_d123_p3_residual_terminal tests.test_v3_residual_authority_migration tests.test_d123_p3_cooling_resume_effect
```

Result: **13 PASS**. Canonical full offline discovery using `/home/home-pc/rd6018-v3-deploy/.venv/bin/python` (Python 3.12) and synthetic `TG_TOKEN=123456789:d123-sprint15`: **2,384 tests, 3 skipped, PASS**. `python -m compileall -q` for the touched Python modules and `git diff --check`: PASS. The requested `/tmp/rd6018-d109-venv/bin/python` remains absent; no environment or dependency was installed. This source-only evidence makes no physical-state or deployment claim.

Remaining IDLE/DONE pending-log/report and persistence ownership, Storage/DONE,
Manual integration, remaining P3, P2, P4, P5, and physical acceptance remain
open.
