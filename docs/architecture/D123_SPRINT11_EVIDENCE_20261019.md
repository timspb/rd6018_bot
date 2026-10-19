# D123 Sprint 11 — PREP to MAIN entry effect

Date: 2026-10-19. Sprint 10 exact source commit: `f0acf98d8d479784885d0f59de0d9b500f22e9c6`. Sprint 11 is a separate source-only increment on the same existing branch. No node104, ESP Native API, HA, firmware, deployment, service, GitHub, release marker, physical output, or live system was accessed or changed.

## Boundary

The residual runtime retains the PREP voltage threshold, target selection and
existing event-end capture. At the accepted threshold, the previous inline
mutation of PREP -> MAIN state and action fields is now expressed by frozen
`PrepCompletionEffect` from `runtime/charge/runtime/prep_completion.py` and one
applicator. The effect preserves the existing canonical target and protection
values, one stage-history edge, restored-target clearing, stage/Ah and start-Ah
clocks, Delta/blanking reset, notification, event-end payload and log event.

The residual scaffold still owns the PREP decision and chooses the targets.
The applicator has no direct RD setters, execution-port access, or Output intent.
The resulting action mapping continues through the same downstream application
execution transaction. PREP's charge threshold/algorithm, Ca/Ca/EFB/AGM target
selection, Manual ownership, cooling behavior, safety, recovery and Guard were
not changed.

## Changed files

- `runtime/charge/runtime/prep_completion.py` — frozen input/effect DTOs, effect
  builder, and single PREP -> MAIN state/action applicator.
- `runtime/charge/runtime/residual_scaffold.py` — delegates PREP completion
  mutation to the typed owner after unchanged threshold/target selection.
- `tests/test_d123_p3_prep_completion_effect.py` — effect parity, deep immutable
  event payload, one stage-history edge, action preservation and static caller /
  physical-writer guards.
- `docs/architecture/D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` — Sprint
  11 evidence and remaining gate status.
- `docs/architecture/D123_CONTROLLER_OWNER_MAP_20261019.md` — PREP entry owner
  and retained boundaries.
- `docs/architecture/D123_SPRINT11_EVIDENCE_20261019.md` — this record.

No controller method was deleted. The PREP threshold decision and
`_prep_target`/`_main_target` selection remain in the residual scaffold; only
the accepted PREP -> MAIN entry mutation moved.

## Verification

- Focused PREP typed-effect and residual authority set: **8 PASS**.
- Full offline discovery after the final source edit:
  **2,373 tests, 3 skipped, PASS**.
- `/home/home-pc/rd6018-v3-deploy/.venv/bin/python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

The required `/tmp/rd6018-d109-venv/bin/python` is absent. As recorded in
Sprint 10 evidence, no replacement environment or dependency installation was
performed; verification uses the already-installed Python 3.12 venv at
`/home/home-pc/rd6018-v3-deploy/.venv/bin/python`, with only the synthetic
`TG_TOKEN=123456789:d123-sprint10`. Python 3.10/3.11 matrix and physical
validation were not performed.

## Remaining gates

- P3: final SAFE_WAIT decision/action construction; remaining residual
  COOLING resume and DONE/IDLE ownership; MAIN + remaining stage cuts; Storage
  and Manual integration; all remaining stage parity/failure/replay guards.
- P2: remaining audit/session lifecycle ownership. MAIN Guard restore admission
  remains deferred and fail-closed unless a source-only proof is possible
  without representing live authority.
- P4/P5, deployment and physical acceptance remain separate pending gates.
