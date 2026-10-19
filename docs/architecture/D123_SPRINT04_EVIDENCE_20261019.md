# D123 Sprint 04 evidence — P2c stage-history cut

Date: 2026-10-19. Workspace: `/home/home-pc/rd6018-d118-start-lease-repair-20261019`.
Starting committed HEAD: `4a56fb7e3088c36c667ee8251af4fa37d472c2ff`.
Interpreter: `/tmp/rd6018-d109-venv/bin/python` (Python 3.12). Token was the
synthetic `TG_TOKEN=123456789:d123-sprint04`.

This was strictly source-only. No SSH, network, GitHub, ESP/HA, firmware,
service, deployment, physical setter, secret, or package operation occurred.
No live state or physical acceptance is asserted.

## Captured route and selected owner cut

Before editing, the method/caller inventory was captured at
`/tmp/d123-sprint04-owner-caller-map.txt`. `runtime.production_runtime` remains
the sole active caller of `ManagedChargeController.tick`; the stage property
also has existing application, persistence, runtime, UI/read-model, guard, and
test consumers. The persistence writer remains `runtime.charge.persistence`
with its existing canonical atomic writer. There is no second FSM or new root.

The stage-history mutation body moved from `ManagedChargeController.current_stage`
to `runtime.charge.session.set_current_stage`. The public property remains stable
and delegates to the session owner. History reconstruction from persisted
`previous_stage`, `last_transition_reason`, and `stage_history` fields and the
three lifecycle history-clear paths now use `runtime.charge.session` operations.
Transition entries retain `from`, `to`, `reason`, and `ts`, the bounded history
length, timestamp behavior, metric reset, reason clearing, and no-op assignment
behavior. `runtime.charge.persistence` remains the serialization boundary and
does not gain a writer.

Added `tests/test_d123_p2c_stage_history.py` for single-edge transition recording,
same-stage no-op behavior, transition metric reset, previous-stage updates,
restore field shape, and a static check against reintroducing the moved bodies.
Existing trace capture/identity, Guard binding, guarded restore, and actuator
failure suites continue to characterize the adjacent contracts.

## Deliberately deferred work

P2c is **incomplete**. `recovery_trace_context`, shadow disagreement repeat
counters/logging, and the lifecycle call into `recovery_trace_store` remain
controller-owned. The recovery trace database module remains the single trace
writer. Moving the remaining lifecycle needs a typed context/capture boundary
and single-writer characterization first. Guarded restore admission ownership
also remains deferred and guarded restore stays fail-closed. Since P2c is not
fully green, no P3 transition-effect construction was attempted.

## Verification

- Focused stage history, controller, production controller, trace identity and
  capture, session Guard binding, guarded restore, and terminal restore suites:
  **63 passed** on the first focused run; the focused architecture/import graph
  suite after aligning the owner import passed.
- Full offline unittest discovery:
  `TG_TOKEN=123456789:d123-sprint04 /tmp/rd6018-d109-venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
  — **2,351 tests run, 2 skipped, all other tests passed** in 118.551s.
  Captured output: `/tmp/d123-sprint04-unittest.log`.
- `/tmp/rd6018-d109-venv/bin/python -m compileall -q .` — passed.
- `git diff --check` — passed.
- Import direction: both existing domain isolation AST guards passed in the
  full run; `runtime.charge` does not import persistence, infrastructure, or the
  controller bootstrap from these new session operations.

## Source delta and status

`charge_controller.py` is 2,287 LOC with 73 method declarations / 72 unique
names (Sprint 03 source: 2,302 LOC, 73 / 72). No threshold, recipe, target,
plateau, lease, protection, Guard, execution, or actuator semantics changed.
Checklist and owner map now record the cut and remaining P2 work. Sprint 01–03
evidence remains historical and unchanged.

Sprint status: stage-history ownership is converged; P2c/P2 remain partial;
P3 was not attempted. No deployment or live physical validation occurred.
