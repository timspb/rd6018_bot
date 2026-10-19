# D123 Sprint 07 — P3-2 DESULFATION -> recovery SAFE_WAIT effect

Date: 2026-10-19. Base: `de99f0f669e8276665864954572c01cec739e217` on the
existing `codex/d118-start-lease-repair-20261019` branch. This was a bounded
source-only cut. No node104 SSH, ESP/HA access, physical command, firmware,
service, deployment, GitHub, secrets, package download, or real network call was
used. Tests used only `/tmp/rd6018-d109-venv/bin/python` and the synthetic
`TG_TOKEN=123456789:d123-sprint07`.

## Source/call map

```text
ManagedChargeController.tick
  -> _apply_authoritative_decision (single existing DESULFATION decision caller)
    -> decide_desulfation(active_elapsed_s=...) [unchanged 2h budget]
    -> COMPLETE_TO_SAFE_WAIT only:
       resolve existing _main_target(temp) and _make_log_event_end(...)
       -> build_desulfation_completion_effect(DesulfationCompletionInput)
       -> apply_desulfation_completion_effect exactly once
          -> validate matching non-empty session ID, finite positive generation,
             exact generation match and DESULFATION source stage
          -> existing session.set_current_stage (one history edge)
          -> commit RecoverySafeWaitContinuation and compatibility mirrors
          -> existing clear targets, stage time/Ah, SAFE_WAIT sample and MAIN
             plateau reset
          -> action mapping to the existing runtime/application execution route
             including turn_off=True; existing verified OFF/readback/rollback
             transaction order remains unchanged
```

The pure builder and applicator live in
`runtime/charge/runtime/desulfation_completion.py`; there is no import to the
controller, actuator setter, execution port, or Output ON effect. The effect
contains session identity/generation, source/next stage, canonical MAIN V/I
target, recovery attempt, AGM step, timestamp, Ah and sample data. Its action
keys are exactly `log_event_end`, `turn_off`, `notify`, and `log_event`; the
notification uses the existing strategy SAFE_WAIT margin. `RecoverySafeWaitContinuation`
remains typed and retains source stage, next stage, stage start, targets, session
generation, recovery attempt and AGM step. `_safe_wait_*` fields remain read
compatibility mirrors. No chemistry target or recipe is hardwired.

`ManagedChargeController._complete_desulfation_to_safe_wait` is removed
entirely. There is one builder and one applicator call site, inside the single
existing `_apply_authoritative_decision` branch. Missing/stale session identity,
missing/non-finite/non-positive generation or wrong current stage returns
without action or mutation. Canonical `decide_desulfation` duration and its
output-off gate are unchanged. No STOP/OFF transaction or recovery restart
owner was changed. The persisted-session integration now reaches the transition
through the canonical decision path and verifies the existing serialization.

## Regression evidence

Focused command set: the new P3-2 module, bounded DESULFATION ownership cutover,
charge authority, recovery authority, verified recovery resume transaction,
voltage-relaxation persisted-session contract and final SAFE_WAIT output
transaction suites: **49 tests PASS**. Coverage includes Ca/Ca, EFB and AGM
canonical target selection; exact action keys/values; single stage-history
edge; typed continuation and compatibility state; target clearing, state clock
and Ah, sample, plateau reset; exact 2h decision boundary; no ON action; missing
and stale ID/generation rejection; single caller; no controller import or
physical setter in the effect owner; OFF/verified transaction, rollback and
restart/persisted-session behavior.

Final full offline discovery on the final source state:

```text
TG_TOKEN=123456789:d123-sprint07 \
  /tmp/rd6018-d109-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
Ran 2361 tests in 103.999s
OK (skipped=2)
```

Log: `/tmp/d123-sprint07-final-unittest.log`. Also PASS:
`/tmp/rd6018-d109-venv/bin/python -m compileall -q .` and `git diff --check`.
No physical state or live behavior was checked or asserted. This source commit
is not deployed or physical acceptance.

## Scope and remaining work

P3-2 is complete on this source branch. P3 remains incomplete: MAIN + PREP and
residual; MIX and final SAFE_WAIT; cooling/storage/done; Manual integration;
and typed stage/effect convergence across those paths remain. P2 remains partial
for MAIN Guard restore admission and remaining audit/session lifecycle
ownership. P4 façade elimination and P5 release/physical acceptance remain
pending. No unrelated migration was started.
