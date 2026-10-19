# D123 Sprint 08 — P3-3 MAIN -> MIX effect

Date: 2026-10-19. Source commit: `f56b8355e82f4ed56b5d930102551e80f3798efa`,
based on clean HEAD `de10411662f47749b4249af6488df0d25a6699ef`. Final source
changes are committed on the existing `codex/d118-start-lease-repair-20261019`
branch. This was source-only work in the existing WSL2 Ubuntu 24.04 workspace.
No network, SSH, ESP/HA, firmware, service, deployment, package installation,
real secret or physical command was used. No physical acceptance is claimed.

## Cut and ownership

```text
ManagedChargeController.tick
  -> _apply_authoritative_decision (sole existing MAIN decision caller)
    -> decide_main_transition (unchanged)
    -> ENTER_MIX only:
       resolve existing _mix_target(temp), _add_phase_limits and event-end data
       -> build_main_mix_effect(MainMixEffectInput)
       -> apply_main_mix_effect exactly once
          -> existing session.set_current_stage (one history edge)
          -> existing restored-target, stage clock/Ah, Delta/blanking,
             plateau and finish-evidence resets
          -> same V/I/OVP/OCP/notification/log action payload
    -> unchanged production action consumer / execution port
       -> existing OFF/ON transaction, verification, rollback and commit
```

`_enter_mix` was deleted with no wrapper. The immutable effect resides in
`runtime/charge/runtime/mix_entry.py`, which imports no controller and has no
actuator or execution-port call. MAIN/MIX decisions, target selection, current
clipping evidence, transaction ownership and safety remain with existing
owners. No recipes, chemistry policy, finish evidence, guard, lease or
physical implementation changed.

## Verification

- Focused typed-effect and regression invocation: **73 PASS**. Includes exact
  effect action/reset parity for Ca/Ca, EFB and AGM; AST single builder and
  applicator callers, deleted method and no actuator ownership; downstream
  MIX current-clipping evidence; final/recovery SAFE_WAIT; verified OFF/ON,
  rollback, trace/checkpoint and persisted-session/restart paths.
- Full offline Python 3.12 discovery using synthetic
  `TG_TOKEN=123456789:d123-sprint08` and
  `/tmp/rd6018-d109-venv/bin/python`: **2,363 tests, 2 skipped, PASS**.
  Log: `/tmp/d123-sprint08-full-unittest.log`.
- `/tmp/rd6018-d109-venv/bin/python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- No multi-version matrix or hardware validation was performed.

## Status

P3-3 MAIN -> MIX entry effect is complete for this source commit only. P3
remains partial: MAIN + PREP and residual, final SAFE_WAIT, cooling/storage/done
and Manual integration remain. P2 remains partial for MAIN Guard restore
admission and remaining audit/session lifecycle ownership. P4/P5 and any
deployment or physical acceptance remain pending.
