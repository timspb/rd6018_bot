# D123 Sprint 17 — residual CV-clock mirror ownership

Date: 2026-10-19. Exact starting HEAD: `e6d27ce067049197c1f60cec75b78ef450601778`.
Work is source-only. No ESP, node104, HA, live system, deployment, service,
GitHub, or physical equipment was accessed.

## Bounded cut and parity

`run_authoritative_residual_scaffold` now delegates its existing `_cv_since`
mirror update to `runtime.charge.runtime.residual_observation.update_residual_cv_clock`.
The call remains after the IDLE early return, so PREP, COOLING, and DONE update
the mirror while IDLE does not. A first CV sample initializes the timestamp;
subsequent CV samples retain it; CC clears it. This removes one residual stage
state mutation from the transitional scaffold without moving persistence,
verified Storage completion, recipes, safety, Guard, lease, execution, or
verified-enable ordering. No RD setters or execution-port calls were added to
charge owners. Session schema and history behavior are unchanged.

The DONE persistence path remains inside the verified completion applicator
because its canonical save is coupled to the verified Storage receipt. That
boundary was not split. Storage/DONE and Manual integration remain pending.

## Changed Sprint 17 files

- `runtime/charge/runtime/residual_observation.py` — CV-clock mutation owner.
- `runtime/charge/runtime/residual_scaffold.py` — single delegation call.
- `tests/test_d123_p3_residual_cv_clock.py` — CV/CC parity and one-call/no-direct-write guards.
- `docs/architecture/D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` — Sprint 17 status.
- `docs/architecture/D123_CONTROLLER_OWNER_MAP_20261019.md` — owner and scope record.

## Verification

Python: `/home/home-pc/rd6018-v3-deploy/.venv/bin/python` (Python 3.12).
Synthetic test environment: `TG_TOKEN=123456789:d123-sprint17`.

Focused isolated Sprint 17 set: **20 PASS**.

Full offline unittest discovery on the isolated Sprint 17 source: **2,391 tests,
3 skipped, PASS**. `python -m compileall -q` for touched modules and
`git diff --check`: PASS. No physical acceptance or deployment claim is made.

## Scope note

During validation, unrelated concurrent work appeared in the shared worktree:
a `stop_diagnose` extraction in `charge_controller.py`, its new owner module,
a Sprint 16 evidence count edit, and a removal of an existing reporting failure
test. These changes are not included in this Sprint 17 cut. They are preserved
in the worktree and excluded from its commit.
