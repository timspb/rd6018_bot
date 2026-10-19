# D123 Sprint 14 — residual IDLE/DONE terminal flow choice

Date: 2026-10-19. Exact starting HEAD: `37b5bf938e3b1bcf50dffb3b0d8503b4e783634c`.
Source-only workspace change. No node104, ESP, HA, live system, deployment,
service, GitHub, or external system was accessed.

## Bounded ownership cut

The active production path remains `runtime.production_runtime` invoking the
single `ManagedChargeController.tick`, which dispatches residual stages through
`_run_stage_scaffold_tick` to `run_authoritative_residual_scaffold`. DONE and
IDLE do not have a distinct automatic transition effect to extract. The
residual observer still performs shared sample, temperature/link safety,
analytics, and logging/report work for these stages. This sprint moves only
the terminal-flow choice into the existing charge runtime package as a frozen
`ResidualTerminalDecision`.

The decision preserves IDLE's existing return immediately after shared
observation/safety handling, before pending-log and stage reporting work. DONE
continues through the existing logging/report path and has no automatic
transition at the bottom of the scaffold. No state mutation, persistence,
session identity, Guard, lease, recipe, Manual behavior, action execution, or
verified transaction ownership moved. `application.execution_port` remains the
sole physical writer.

## Changed files

- `runtime/charge/runtime/residual_terminal.py` — immutable terminal-flow
  decision and unsupported-stage rejection.
- `runtime/charge/runtime/residual_scaffold.py` — one call site for IDLE/DONE
  terminal policy; shared observation remains unchanged.
- `tests/test_d123_p3_residual_terminal.py` — parity, rejection, single-call,
  and no-physical-writer static guards.
- `docs/architecture/D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` —
  records the bounded cut and remaining work.
- `docs/architecture/D123_CONTROLLER_OWNER_MAP_20261019.md` — records actual
  call path, ownership limits, and regression gates.

## Focused verification

Command, using `/home/home-pc/rd6018-v3-deploy/.venv/bin/python` and synthetic
`TG_TOKEN=123456789:d123-sprint14`:

```bash
python -m unittest tests.test_d123_p3_residual_terminal tests.test_v3_residual_authority_migration tests.test_d123_p3_cooling_resume_effect
```

Result: **11 PASS**.

Canonical full offline discovery run directly in WSL outside the Codex workspace sandbox: **2,382 tests, 3 skipped, PASS**. `python -m compileall -q .` and `git diff --check` both PASS. Physical acceptance and deployment were not performed or claimed.

DONE/IDLE shared observation and persistence ownership, Storage/DONE, Manual
integration, remaining P3 work, P2, P4, P5, and physical acceptance remain
open.
