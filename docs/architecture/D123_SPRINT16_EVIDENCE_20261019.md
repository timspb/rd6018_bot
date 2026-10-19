# D123 Sprint 16 — residual pending-log and reporting effect

Date: 2026-10-19. Exact starting HEAD: `ea7c83eb847f172cb0c22160abefefe076a0f9c3`.
Source-only workspace change. The starting branch was `codex/d118-start-lease-repair-20261019`
with a clean worktree. No reset, rebase, node104, ESP, HA, deployment, service,
GitHub, or external system access was performed.

## Bounded ownership cut

The production caller remains `ManagedChargeController._run_stage_scaffold_tick`
through `run_authoritative_residual_scaffold`. Sprint 16 moves one separable
IDLE/DONE residual reporting mutation into `runtime.charge.runtime.residual_reporting`.
The frozen `ResidualReportingEffect` carries pending-log consumption and the
hourly report payload/schedule decision; its applicator clears the pending log,
advances the report timestamp, and routes the report into the action mapping or
the existing direct notification path.

Parity is retained: IDLE returns before pending-log/report processing; DONE
continues through it. The report interval, disabled behavior during manual-off,
formatted fields, and behavior when a notification already exists are
preserved. Stage timing, phase-log timing, persistence/session save,
Storage/DONE verified completion, Manual, recipes, safety, and physical routing
remain at their prior owners. No RD setters or `execution_port` calls were
introduced in the charge owner.

## Changed files

- `runtime/charge/runtime/residual_reporting.py` — frozen decision/effect and
  one applicator for pending-log and hourly-report state/output.
- `runtime/charge/runtime/residual_scaffold.py` — one build/apply path; former
  inline pending-log/report mutation removed.
- `tests/test_d123_p3_residual_terminal.py` — parity, failure/edge behavior,
  immutable effect, one-call and static no-writer guards.
- `docs/architecture/D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` —
  Sprint 16 verified status and remaining P3 work.
- `docs/architecture/D123_CONTROLLER_OWNER_MAP_20261019.md` — actual owner
  change, parity boundary, and next-gate assessment.

## Verification

Python: `/home/home-pc/rd6018-v3-deploy/.venv/bin/python` (Python 3.12).
Synthetic environment token: `TG_TOKEN=123456789:d123-sprint16`.

Focused command (with `PYTHONPATH=tests` for the existing SAFE_WAIT test helper):

```bash
PYTHONPATH=tests TG_TOKEN=123456789:d123-sprint16 \
  /home/home-pc/rd6018-v3-deploy/.venv/bin/python -m unittest \
  tests.test_d123_p3_residual_terminal \
  tests.test_v3_residual_authority_migration \
  tests.test_d123_p3_cooling_resume_effect \
  tests.test_done_storage_restore \
  tests.test_final_safe_wait_output_transaction
```

Result: **30 PASS**.

Full offline discovery:

```bash
TG_TOKEN=123456789:d123-sprint16 \
  /home/home-pc/rd6018-v3-deploy/.venv/bin/python -m unittest discover \
  -s tests -p 'test_*.py'
```

Result: **2,387 tests, 3 skipped, PASS**. `python -m compileall -q .` and
`git diff --check` also passed. `/tmp/rd6018-d109-venv/bin/python` is absent;
no environment or dependency was installed. No physical state or deployment
claim is made.

## Remaining gate

IDLE/DONE persistence ownership, Storage/DONE integration, Manual integration,
remaining central-controller stage application and tick orchestration, P2, P4,
P5, and later physical acceptance remain open. No additional Sprint 17 cut was
made: the nearest Storage/DONE boundary is coupled to verified completion and
canonical persistence, while the other candidates are broader than a safe
source-only slice with clear parity in this sprint.
