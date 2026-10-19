# D123 Sprint 06 — P3-1 MAIN -> DESULFATION effect

Date: 2026-10-19
Base: `a679133caf7a20d2045fbc4708570ab82664e34f` (Sprint 05 committed HEAD)
Scope: source-only bounded ownership cut in the existing WSL2 Ubuntu 24.04
workspace. No SSH, network, ESP Native, HA, firmware, service, package
installation, secrets, deployment, or physical command was used. No Output
state was changed. This report is not physical acceptance.

## Exact source and target call graph

```text
runtime.production_runtime production tick
  -> ManagedChargeController.tick
    -> _apply_authoritative_decision
      -> decide_main_transition (unchanged pure decision owner)
      -> ENTER_DESULFATION only:
         resolve existing compensated DESULFATION target and log_event_end
         -> build_main_desulfation_effect(MainDesulfationEffectInput)
            pure, frozen typed effect and read-only action mapping
         -> apply_main_desulfation_effect exactly once
            -> runtime.charge.session.set_current_stage (single history writer)
            -> existing restored-target, delta/blanking and evidence reset helpers
            -> update existing attempt count, stage clocks/Ah and phase limit
    -> existing action dictionary consumer in runtime.production_runtime
      -> application.execution_port.execute_controller_actions
         -> existing ordered OVP/V/I/OCP and safe-output transaction/verification
      -> existing verified stage commit boundary
```

`ManagedChargeController._enter_desulfation` no longer exists. The controller
has one `apply_main_desulfation_effect` call site, in the existing
`ENTER_DESULFATION` dispatch. The effect module has no reverse controller import
and no actuator/transport/execution-port calls. No other `_enter_*` transition
was moved. The existing 900 s lease, MAIN Guard/Iset ratchet, verified execution
route and rollback/restart admission remain governed by their existing owners.

## Before/after parity

The old controller method and new effect preserve the same seven action keys:
`log_event_end`, `set_voltage`, `set_current`, `set_ovp`, `set_ocp`, `notify`,
`log_event`. Values retain the prior meanings: event-end record from the same
inputs; target from `select_desulfation_target` plus the same temperature
compensation; OVP = target voltage + existing OVP margin; OCP = target current
+ existing DESULFATION OCP margin; same Russian HTML notification format and
`START | V2_DESULFATION` event. At 25 C the strategy target remains 16.3 V;
for a 90 Ah example current remains 1.8 A and resulting OVP/OCP remain 16.4 V /
2.8 A. For 60 Ah, current remains 1.2 A and OCP 2.2 A. These examples do not
change any battery recipe or threshold.

The application still applies one stage assignment, so stage history receives
one `from`/`to`/existing reason/timestamp entry through the existing session
helper. The effect applies the prior antisulfate increment, stage start time and
Ah, restored-target clear, delta/blanking reset, plateau evaluator reset and
phase current limit update. No setter is called by the effect owner; it only
returns action intents for the established downstream execution route. The
existing 15/40-minute plateau logic, retry budget/guard, recovery SAFE_WAIT
continuation, pause/restore logic, terminal stop, transaction rollback and
restart safety paths are unchanged.

## Regression and verification

New focused coverage: `tests/test_d123_p3_main_desulfation_effect.py` (3 tests)
checks Ca/Ca, EFB and AGM target/action parity, immutable effect mappings,
single session-history edge and state reset parity, removed controller method,
single effect caller and import direction.

Additional focused invocations (86 tests across invocations, with the new
three-test module included in the DESULFATION pattern run): charge authority,
MAIN authority, recovery authority, DESULFATION bounded stage, recovery and
final SAFE_WAIT output transactions, session atomic Guard binding, MAIN Guard
runtime, and the existing domain/import architecture guards. These cover the
3/4 attempt limits and stage authority guard, verified-output transaction
failure/rollback, retained current/OCP ownership, terminal stop, restart and
recovery continuation behavior.

Final required offline discovery, using only the synthetic local token
`TG_TOKEN=123456789:d123-sprint06` and existing
`/tmp/rd6018-d109-venv/bin/python`:

```text
Ran 2358 tests in 102.645s
OK (skipped=2)
```

Also PASS: `python -m compileall -q .`, targeted owner/import guards, and
`git diff --check`. One earlier full run exposed the new module importing
`controller_state` against existing domain isolation guards; that dependency
was removed in favor of the already-existing state helper seam, and the final
full run and architecture guards passed.

## Remaining scope and risks

This is **P3-1 only**, not P3 completion. `_apply_authoritative_decision`,
`tick`, and all other stage effect methods remain in the transitional
`ManagedChargeController`; application orchestration has not yet been migrated.
The controller still computes the target and event-end data before pure effect
construction, while the typed effect owns the action shape and single state
application. Later P3 cuts remain: MAIN/PREP and residual; DESULFATION completion
and recovery SAFE_WAIT; MIX and final SAFE_WAIT; cooling/storage/done; Manual
integration. P2 remains partial for MAIN Guard restore admission and remaining
audit/session lifecycle ownership.

The local automated suite is software evidence only. Production remains on
D122; no deployment, physical acceptance, or live stage behavior is claimed.
