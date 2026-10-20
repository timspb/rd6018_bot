# D123 Sprint 52 — production session extension convergence

Status: source-only P4 migration on `codex/d118-start-lease-repair-20261019`.
No node104, ESP, HA, firmware, service, deployment, GitHub, or physical output
was accessed or changed.

## Source identity and result

- Starting exact HEAD: `3ad81893e300bd73d0e8d2bc08cdb974bb4687b0`.
- The code and evidence could not be committed in this workspace. Git failed to
  create `/home/home-pc/rd6018-safety-arch-20261016/.git/worktrees/rd6018-d118-start-lease-repair-20261019/index.lock`
  with `Read-only file system`; the configured `.git` metadata is outside the
  writable workspace. HEAD therefore remains the starting SHA and the worktree
  is modified. No permission bypass was attempted.
- Production class AST declarations: **22 before → 10 after**.
- Overrides of `ManagedChargeController`: **10 before → 8 after**.
- Focused controller/cooling/recipe/session/Guard/application regression set:
  **66 PASS**. The final architecture/recipe guard subset also passed **7/7**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Full Python 3.12 offline discovery using
  `/home/home-pc/rd6018-v3-deploy/.venv/bin/python`: **2,451 tests,
  2,443 PASS / 3 skipped / 5 errors**. A temporary test-process selector poll
  cap was needed because this environment otherwise leaves `aiosqlite` worker
  callbacks undelivered while the event loop waits indefinitely. The five
  remaining errors are environment limits: one nested unittest subprocess
  timed out because it does not inherit that process-local workaround; three
  tests could not bind Unix sockets (`PermissionError: Operation not permitted`);
  and one local loopback HTTP fixture could not bind TCP for the same reason.
  No tests were skipped or weakened to produce this result.

## Dependency map at the starting SHA

### Production methods overriding `ManagedChargeController`

The starting production class overrides:
`__init__`, `_new_runtime`, `_prep_target`, `_main_target`, `_desulf_target`,
`_mix_target`, `_get_target_v_i`, `_apply_continuous_tail_hold`, `_save_session`,
and `try_restore_session` (10 methods).

After this migration, the overrides are:
`__init__`, `_new_runtime`, `_prep_target`, `_main_target`, `_desulf_target`,
`_mix_target`, `_get_target_v_i`, and `try_restore_session` (8 methods).
`_session_document_extensions` is a canonical persistence host hook, not a
base-class override.

### Inherited state and active inherited behavior

- `ManagedChargeController.__init__` initializes the only FSM/session host,
  including stage, timer, target, trace identity, continuation and Guard fields.
- `start`, `stop`, `_save_session`, `full_reset`, `current_stage`, and diagnostic
  accessors remain inherited. Production runtime calls inherited `_save_session`,
  `stop`, `full_reset`, timer/snapshot methods, target/finish-policy methods, and
  `try_restore_session` through the same `charge_controller` object.
- `_new_runtime` selects `CoolingAwareShadowRecoveryRuntime`; inherited start and
  restore lifecycle call that method on the same host.
- The five production target adapters continue to use base recipe selectors and
  temperature compensation, then apply `application.production_target_policy`.
  Target/recipe policy has not changed.
- `_save_session` now directly inherits the canonical atomic persistence method.
  Session extension fields are supplied through the thin
  `_session_document_extensions` host hook.

### Production-only mutable fields and session extensions

Production-specific mutable fields stay on the one host:
`_v2_continuous_tail_since`, `_v2_continuous_tail_stage_start`,
`_v2_cooling_pause`, `_finish_evidence`, `_delta_reported`, and
`_delta_trigger_mode`. Existing base-owned session/runtime signal context and
Guard/trace state remain where they were.

`application.production_session_extensions` now owns tail-hold calculation and
reset, cooling pause capture/resume, runtime-signal snapshot and reconstruction,
finish-evidence validation and restore, extension-document construction, and
operator notification projection. The serialized keys remain unchanged:
`v2_cooling_pause`, `runtime_signal`, `delta_state_version`,
`delta_session_id`, `delta_reported`, `delta_trigger_mode`, and
`finish_evidence`. `runtime.charge.persistence` and
`runtime.charge.session_atomic` remain the sole canonical document/atomic writer.
The moved functions only operate on the existing host; they introduce no FSM,
session object, state graph, actuator writer, or persistence writer.

## Cuts made

1. Moved production uninterrupted tail residence from the controller override to
   `apply_continuous_tail_hold`; non-production base hosts retain identity
   assessment behavior.
2. Moved cooling pause capture/resume orchestration and runtime-signal snapshots
   to the existing application tick owner. Cooling clocks, saved targets,
   post-cooling OFF behavior, reset semantics, and pause duration remain intact.
3. Moved runtime-signal and finish-evidence validation/restore plus session
   extension serialization into the application extension module. The production
   controller keeps only the persistence hook adapter; restore ordering and
   Guard admission are unchanged.
4. Moved operator reason/text projection to the application extension owner.
   AUTO subclasses still supply their existing reason map as data.
5. Removed the no-op `_save_session` wrapper so the existing canonical writer is
   inherited directly.

Static architecture gates reject reintroducing these methods into production,
AUTO, or Diagnostic controller subclasses; prohibit direct physical/session
writers in the extension owner; and require that the extension module define no
second class/state owner. Existing composition tests retain the single runtime
host constructor gate.

## Remaining P2 boundary and P4 status

P4 inheritance is **not complete**. The exact residual overrides are:

- `__init__`: delegates canonical controller/session state initialization to
  the base and adds the production-only fields listed above.
- `_new_runtime`: chooses the cooling-aware evidence runtime during inherited
  START/restore lifecycle.
- `_prep_target`, `_main_target`, `_desulf_target`, `_mix_target`,
  `_get_target_v_i`: adapt existing inherited target selection to the already
  composed recipe-envelope policy while operating on inherited session state.
- `try_restore_session`: calls canonical base persistence restore, then applies
  legacy intent defaults, Guard journal reconstruction, finish/runtime signal
  restore, target bounding, and fail-closed cooling continuation validation in
  the current order.

The ordinary restore document is intentionally still the canonical raw-document
handoff retained by `runtime.charge.persistence`. Base restore uses it for
DESULFATION timing, continuations, and identity enrichment; production restore
uses the same bytes for Guard and MIX extension reconstruction. Replacing this
handoff or removing the host inheritance now crosses the documented P2
session/state/lifecycle boundary. MAIN Guard restore admission remains
fail-closed/deferred. There is no evidence authorizing a different admission
policy. See the Sprint 30 restore seam evidence and `D123_CONTROLLER_OWNER_MAP_20261019.md`.

P5 remains open: commits/clean Git state could not be produced under the
read-only Git metadata mount; the Python 3.10/3.11 matrix and separately
authorized physical acceptance also remain outstanding. This sprint asserts no
physical validation.
