# D123 Sprint 02 evidence — P2 partial trace/signal context cut

Date: 2026-10-19. Worktree: `/home/home-pc/rd6018-d118-start-lease-repair-20261019`.
Starting source SHA: `7dde73377f032858d395d810d8490522a7350e9b` (the requested clean
HEAD). This is source-only work. No SSH, HA, ESP Native connection, physical
device, service, firmware, deployment, GitHub, package installation, or secret
access occurred. Node104 was left alone as requested.

## Boundary audit and selected cut

The active production graph remains one `runtime.production_runtime` instance
calling `ManagedChargeController.tick` (`runtime/production_runtime.py:2941`).
`tick` still owns the stage scaffold, `RecoveryTracePoint` observation, evidence
decisions, stage mutation/application, and action result. P2 does not move any
of those lifecycle decisions.

Moved to `runtime.charge.evidence.trace_context` as pure assembly with frozen
typed inputs:

- finite numeric/output normalization used by trace assembly;
- stable `RecoveryTracePoint` companion metadata (`trace_point` payload);
- CV/CC `_v2_session_signal_context` assembly, including Imin/Vmax clocks,
  reversal confirmation state, telemetry timestamp/age and output state;
- shadow event/metrics and first-stage/authority metadata assembly.

The production tick invokes each moved builder once on its normal success path;
the signal context has exactly one assembly call. The existing
`RecoveryTracePoint`, `recovery_shadow` structure, keys and physical output
provenance are preserved. The error path uses the same trace metadata builder.
No application, UI, serialization schema, safety or execution interface changed.

Stateful or durable behavior stays put: `_log_shadow_disagreement` mutates its
repeat counters and logs; `_begin_trace_identity`, `_initialize_shadow_session`,
`_write_trace_identity_to_session_file`, `_restore_trace_identity`, identity
context, and recovery runtime creation remain controller lifecycle. In
particular, the trace identity writer currently performs its own direct file
replacement. Moving that writer without coordinating it with the existing
canonical atomic session writer and Guard journal risks competing session
documents, so identity/restore was deliberately not moved. P2 is **partial**;
there is no claim that the facade or tick ownership is removed.

## Source metrics

| Metric | Before (requested SHA) | After source cut |
|---|---:|---:|
| `charge_controller.py` LOC | 2,529 | 2,397 (-132) |
| `ManagedChargeController` AST method declarations | 84 | 78 (-6) |
| Unique method names | 83 | 77 (-6) |
| New evidence owner | — | `trace_context.py`, 182 LOC |

The sole runtime tick call remains `runtime.production_runtime:2941`;
`charge_controller.py` contains no self-recursive/external `.tick()` calls.
Static AST tests prevent the transferred assembly methods from returning and
assert the singular signal-context and expected tick builder call counts.

## Tests and checks

- Focused: **66 passed** across the new direct context tests and controller,
  trace identity/restart, atomic session/Guard binding, recovery shadow/session,
  signal diagnostic, output-off gating and final SAFE_WAIT suites.
- Full offline unittest discovery: **2,343 passed, 2 skipped** in 121.436s;
  uses only `TG_TOKEN=123456789:offline-d123-p2` and
  `/tmp/rd6018-d109-venv/bin/python` (Python 3.12.3). The first full run exposed
  two diagnostic MIX tests still calling the removed controller normalizer;
  that external observation path now imports the same canonical evidence
  function directly, and the full rerun passes.
- `compileall -q .`, import/AST ownership checks, and `git diff --check` run
  locally; no new dependency was added. The evidence module imports existing
  evidence/decision types; neither imports the controller or application,
  leaving the production dependency direction acyclic.
- Existing `test_recovery_trace_identity` confirms saved identity survives
  restore/re-estimation; `test_session_atomic_guard_binding` confirms one
  canonical atomic session document and intact Guard continuity. These remain
  regression gates; identity ownership itself is not yet converged.

No physical result, Native readback, deployment acceptance, or D122/D123 live
behavior assertion is made by this source-only sprint.

## Remaining work

1. Finish P2 session identity/restore and stage-history ownership by routing
   identity enrichment through the canonical session writer, retaining the
   current serialized field names and guarded restore semantics. Keep one
   durable writer and prove restart and negative restore behavior.
2. Move remaining observation state such as disagreement counters/logging and
   trace persistence through existing owners without adding another journal.
3. P3 remains stage decision/effect/tick application convergence in the existing
   application and charge owners; preserve the single execution port and all
   current safety/lease/recipe behavior.
