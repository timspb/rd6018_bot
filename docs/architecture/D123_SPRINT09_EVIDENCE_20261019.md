# D123 Sprint 09 — P3-4 final SAFE_WAIT entry effect

Date: 2026-10-19. Source baseline: `49e53554289da2052587dd6e81a7cf5c32c943bc`
on the existing `codex/d118-start-lease-repair-20261019` branch. The source
effect and this evidence are committed together; the exact resulting SHA is
reported in the task handoff. This was source-only work in the
requested WSL2 Ubuntu 24.04 workspace. No node104, SSH, ESP Native API, HA,
firmware, service, hardware, GitHub, network, dependency installation or real
secret was accessed. A synthetic local `TG_TOKEN=123456789:d123-sprint09` was
used for tests. D122/live operation was not touched or re-read; this evidence
makes no physical-state or acceptance claim.

## Boundary and preserved behavior

```text
unchanged MAIN/MIX strategy decision: COMPLETE_TO_SAFE_WAIT
  -> existing storage target + event-end payload selection
  -> frozen FinalSafeWaitEntryEffect
  -> one mutation applicator in runtime.charge.runtime.final_safe_wait_entry
       -> identity/source/generation validation before mutation
       -> one session stage-history edge and final SAFE_WAIT continuation
       -> same sample/reset bookkeeping and original log/notify/OFF intents
  -> unchanged action consumer / execution port
       -> verified OFF and existing final SAFE_WAIT continuation decision
       -> existing verified Storage ON commit or OFF rollback
```

The effect carries source stage, session ID/generation, selected Storage
targets, completion reason, event-end data, sample values and timestamp. Its
action mapping preserves `log_event_end`, the existing completion notification,
`START | V2_AUTHORITATIVE`, and `turn_off=True`. Acceptance clears restored
targets, updates stage/Ah clocks and SAFE_WAIT target mirrors, records the same
sample, resets the completed sticky finish hold and MAIN plateau evidence, and
clears the recovery continuation. The existing pure MAIN/MIX decisions, MIX
finish hold, Ca/Ca/EFB/AGM policies, target selectors, OFF/readback/rollback
ordering, persisted schema, lease and Guard were not changed.

The applicator rejects a missing or stale session ID/generation, invalid target
identity, or wrong source stage before any mutation or action emission. The
existing callers route rejection to STOP_AND_DIAGNOSE; that path requests OFF
and cannot request ON. `_enter_safe_wait_done` is deleted; no wrapper remains.
The owner has no direct hardware setter or execution-port dependency. The
existing controller decision path and AUTO decision adapter both use the same
typed effect owner.

## Verification

- Focused entry parity and adjacent final SAFE_WAIT, persisted continuation,
  verified enable and authority regression: **23 PASS**.
- Focused final SAFE_WAIT/recovery/MIX/readback/lease/rollback-related
  transaction/restoration families: **469 PASS**.
- Static AST gate checks the single mutation-applicator call boundary, absence
  of direct physical writers, and deletion of `_enter_safe_wait_done`.
- Full offline discovery with
  `TG_TOKEN=123456789:d123-sprint09 /tmp/rd6018-d109-venv/bin/python -m unittest discover -s tests -p 'test_*.py'`:
  **2,367 tests, 2 skipped, PASS**. Log: `/tmp/d123-sprint09-full-unittest.log`.
- `/tmp/rd6018-d109-venv/bin/python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python 3.10/3.11 matrix and physical validation were not performed.

## Remaining work

This completes only the final SAFE_WAIT entry effect. Final SAFE_WAIT decision
and verified completion commit, MAIN + PREP and residual, cooling/storage/done,
and Manual integration remain P3 work. P2 remains partial for MAIN Guard restore
admission and remaining audit/session lifecycle ownership. P4/P5, deployment,
physical validation and production acceptance remain pending.
