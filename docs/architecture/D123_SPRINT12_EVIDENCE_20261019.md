# D123 Sprint 12 — final SAFE_WAIT authority effect

Date: 2026-10-19. Starting source baseline: Sprint 11 commit
`15405d2` (`refactor(charge): extract prep completion effect`) on the existing
`codex/d118-start-lease-repair-20261019` branch. This is source-only work. No
node104, ESP Native API, HA, firmware, deployment, service, release, physical
output, or external system was accessed or changed.

## Boundary and ownership

Both existing callers of
`ManagedChargeController._apply_final_safe_wait_authority` retain their current
route. The controller still normalizes Output state, captures a SAFE_WAIT sample
only when Output is confirmed off, handles invalid continuation with the existing
STOP_AND_DIAGNOSE containment, logs the request, and maps the result to the
existing authority decision.

Continuation validation, relaxation decision, and construction of the exact
Storage request action fields now belong to the frozen
`FinalSafeWaitAuthorityEffect` builder in
`runtime/charge/runtime/final_safe_wait_authority.py`. This owner is pure with
respect to controller state and has no physical writer, execution-port, persistence,
or stage-commit access. The effect actions travel through the existing production
action router and `application.execution_port`; verified receipt routing and the
DONE effect remain as before. The receipt is still the only route to commit DONE.

## Changed files

- `runtime/charge/runtime/final_safe_wait_authority.py` — frozen effect and
  validation/decision/request builder.
- `charge_controller.py` — route both call paths through the effect owner while
  retaining sample capture and fail-closed orchestration.
- `tests/test_d123_p3_final_safe_wait_authority_effect.py` — exact action parity,
  wait/rejection behavior, and single builder-call guard.
- `docs/architecture/D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` — Sprint
  12 progress and remaining work.
- `docs/architecture/D123_CONTROLLER_OWNER_MAP_20261019.md` — ownership and
  caller boundary.
- `docs/architecture/D123_SPRINT12_EVIDENCE_20261019.md` — this record.

## Verification

- Focused final SAFE_WAIT authority, mix authority, final transaction and Storage
  restore set: **27 PASS**.
- Full offline discovery outside the Codex workspace sandbox: **2,376 tests, 3 skipped, PASS**.
- python -m compileall -q .: PASS.
- git diff --check: PASS.
- The workspace-sandbox run tripped the unrelated autonomous resource-lifetime subprocess contract; the canonical direct WSL run passed cleanly.

Results are source-only and do not establish physical acceptance.

Remaining P3 includes residual COOLING resume, DONE/IDLE and Manual integration.
P2 remains partial; P4/P5 and separate physical acceptance remain open.
