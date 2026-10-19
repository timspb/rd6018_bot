# D123 Sprint 13 — residual COOLING resume effect

Date: 2026-10-19. Exact starting HEAD: `b197af27fb2ef24e932fed06d445c710d348ea3a`.
Source-only workspace change. No node104, ESP, HA, live system, deployment,
service, GitHub, or external system was accessed.

## Bounded ownership cut

The actual production caller is `ManagedChargeController._run_stage_scaffold_tick`,
which routes residual PREP/COOLING/IDLE/DONE to the existing
`run_authoritative_residual_scaffold`. The COOLING branch previously performed
resume stage mutation, timing resets, target action construction, phase limits,
and notification/log values inline. Sprint 13 moves only the resume transition
effect into the existing `runtime.charge.runtime` package as a frozen typed
`CoolingResumeEffect`.

The residual scaffold still owns the cooling threshold, source event capture,
phase limit generation and notification dispatch. Actions continue through the
existing production action route; `application.execution_port` remains the sole
physical writer and verified transaction boundary. The effect has no setter or
execution-port calls. Target values, return-stage fallback, stage/Ah clock,
cooling source clearing, blanking deadline, action keys/values, session history
edge, and stale-stage rejection are covered. No recipe, lease, Guard, session,
safety, START, or Manual semantics were intentionally changed.

## Changed files

- `runtime/charge/runtime/cooling_resume.py` — frozen effect and one applicator.
- `runtime/charge/runtime/residual_scaffold.py` — sole existing COOLING caller
  builds/applies the effect.
- `tests/test_d123_p3_cooling_resume_effect.py` — parity, failure and static
  ownership guards.
- `docs/architecture/D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` — cut
  status and remaining P3 work.
- `docs/architecture/D123_CONTROLLER_OWNER_MAP_20261019.md` — actual route and
  ownership record.

## Verification

- Focused command with synthetic `TG_TOKEN=123456789:d123-sprint13` using
  `/home/home-pc/rd6018-v3-deploy/.venv/bin/python`: **22 PASS** across the new
  effect test, residual authority migration, production cooling contract, and
  desulfation ownership cutover.
- Canonical full offline discovery run directly in WSL outside the Codex workspace
  sandbox: **2,379 tests, 3 skipped, PASS**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Physical acceptance and deployment are not performed or claimed.

DONE/IDLE ownership, Storage/DONE and Manual integration remain P3 work. P2
remains partial; P4/P5 and separate physical acceptance remain open.
