# D123 Sprint 10 — final SAFE_WAIT verified completion effect

Date: 2026-10-19. Starting exact clean HEAD: `f35d086f3166e94f8a15eccedc3da583e999c7ad` on the existing `codex/d118-start-lease-repair-20261019` branch. This is source-only work. No node104, ESP Native API, HA, firmware, deployment, service, GitHub, release marker, physical output, or live system was accessed or changed.

## Boundary

After the existing `application.execution_port` transaction verifies the
session-bound Storage enable, `ManagedChargeController.commit_verified_enable_transition`
previously validated the final continuation and directly committed SAFE_WAIT ->
DONE, cleared continuation state, and persisted the existing Storage-on intent.
The final completion mutation is now owned by
`runtime/charge/runtime/final_safe_wait_completion.py` as a frozen
`FinalSafeWaitCompletionEffect` with one applicator. The controller retains the
same receipt-routing method and the separate recovery SAFE_WAIT -> MAIN branch.

The effect owner preserves continuation/session ID, generation and start-time
checks before mutation. On acceptance, it applies the same DONE stage edge,
restored-target clearing, stage/Ah clock update, SAFE_WAIT mirror clearing,
continuation clearing, DONE source marker, and canonical session save. The
existing stage-history owner remains responsible for the one history edge, and
the completion source marker is cleared in `finally` even if the save fails.
The effect carries immutable completion result fields only; it has no action
intents, physical setters, or execution-port dependency. The physical verified
transaction still precedes this commit. Main Guard, lease, recipes, profile
ownership, session keys, and recovery behavior are unchanged.

## Changed files

- `charge_controller.py` — final completion branch delegates to the typed
  effect builder/applicator; `commit_verified_enable_transition` remains the
  existing receipt router and recovery commit owner.
- `runtime/charge/runtime/final_safe_wait_completion.py` — new frozen input and
  effect DTOs, validation builder, and one DONE mutation/session-save applicator.
- `tests/test_d123_p3_final_safe_wait_completion_effect.py` — parity, immutable
  result, stale/missing receipt read-only rejection, single history edge, sole
  caller and physical-writer AST guards.
- `docs/architecture/D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` — Sprint
  10 status/evidence and remaining final SAFE_WAIT decision work.
- `docs/architecture/D123_CONTROLLER_OWNER_MAP_20261019.md` — exact new owner
  and retained boundaries.
- `docs/architecture/D123_SPRINT10_EVIDENCE_20261019.md` — this record.

No controller method was deleted in this cut. The direct final completion
mutation block was removed from `commit_verified_enable_transition`; the
method remains for route selection and recovery completion. The final SAFE_WAIT
decision, enable request assembly, residual stages, cooling/Storage/DONE
integration, Manual integration, and application-owned tick remain pending.

## Verification

- Focused final completion, final SAFE_WAIT transaction/restore, MIX authority,
  recovery output transaction and Guard binding set: **30 PASS**.
- Full offline discovery: **2,370 tests, 3 skipped, PASS**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

The requested interpreter `/tmp/rd6018-d109-venv/bin/python` was absent from
the workspace, and the exact required discovery command was attempted but could
not start (`No such file or directory`). No environment or dependency was
created/installed. Tests and compileall were run with the already-installed
`/home/home-pc/rd6018-v3-deploy/.venv/bin/python` (Python 3.12) with the
synthetic token `TG_TOKEN=123456789:d123-sprint10` and no network-backed
services. Python 3.10/3.11 matrix and physical validation were not performed.

## Remaining gates

- P3: final SAFE_WAIT decision/effect request construction; MAIN + PREP and
  residual; cooling/Storage/DONE and Manual integration; remaining typed stage
  decisions/effects and source parity/failure/replay gates.
- P2: remaining audit/session lifecycle ownership. MAIN Guard restore admission
  remains deferred and fail-closed unless a source-only proof can be made
  without representing live authority.
- P4/P5 and separate physical acceptance remain open. This source result is not
  deployment or physical acceptance.
