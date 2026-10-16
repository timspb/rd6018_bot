# D078 Safety Ownership Normalization (2026-10-16)

Status: current-source audit and focused software change at `cd57aa1` (D077 / PR #98).
This note describes code at that baseline and the D078 local delta; it does not
supersede the current architecture/runbook authorities listed in `docs/README.md`.

## Active owner map

- **Safety policy:** `runtime/safety/engine.py::SafetyEngine.evaluate` validates
  a charge intent and returns a decision; `evaluate_evidence` combines diagnostic
  evidence. It is pure policy. `runtime/safety/variables.py` owns the production
  watchdog and envelope variables. Do not treat the historical root
  `runtime_safety.py::RuntimeSafetyGuard` or
  `managed_runtime_safety.py::ManagedRuntimeSafetyGuard` as the new V3 policy
  owner: they remain live adapter/containment boundaries in the production
  migration. `runtime_safety_strict.py::StrictRuntimeSafetyGuard` binds the
  independent edge lease; `managed_runtime_safety.py::ManagedRuntimeSafetyGuard`
  extends that strict guard with managed runtime containment.
- **Charge strategy:** `charge_controller.py::ManagedChargeController` is the
  transitional production facade/state owner; its current automatic behavior
  delegates to modular strategy/runtime functions. MAIN strategy lives under
  `runtime/charge/strategy/main.py` and its helpers. The dormant MAIN ratchet
  is pure in `main_current_guard.py::MainCurrentGuard.observe/commit` and checks
  only propose; `main_guard_pre_on.py::assess_main_guard_before_output_on`
  reconciles persisted/native state without granting ON. MIX policy and CV/CC
  evidence live in `strategy/mix.py::MixPolicy`, `CCMixExitPolicy.evaluate`,
  `CVMixExitPolicy.evaluate`; native current clipping proof is in
  `strategy/mix_current_evidence.py::classify_mix_current_clip` and the
  D076/D077 propagation/replay tests. D077 makes advancing native report
  evidence and owner-issued committed cap proof necessary; uncertain clipping
  censors Delta rather than fabricating ordinary CC/Delta evidence.
- **Pre-ON/session:** `strategy/main_guard_pre_on.py` is the pure Guard-specific
  reconciliation; START preflight and execution are application owners in
  `application/start_preflight.py` and `application/production_start_execution_port.py`.
  Session lifecycle is `runtime/charge/session.py`; session serialization,
  confirmed save and restore policy are `runtime/charge/persistence.py::save_session`
  and `restore_session`. The MAIN Guard reduction transaction is
  `application/main_guard_transaction.py::execute_main_guard_reduction`,
  reached only through `ExecutionPort.execute_main_current_guard_reduction`;
  production does not install it.
- **Single writer/readback:** `application/execution_port.py::ExecutionPort`
  delegates to the app's existing execution owner and verifies returned or
  native readback. `application/guard_execution_owner_lock.py::GuardExecutionOwnerLock`
  serializes participating lifecycle operations. `main_guard_transaction.py`
  owns its protected decrease transaction and durable pending/commit ordering.
- **Composition:** `runtime/production_runtime.py` owns canonical runtime
  construction and production callback/lifecycle wiring; `bot.py` hands off to
  `ProductionComposition`. Do not add another root or install the opt-in Guard
  path from D078.
- **Physical lease/transports:** `edge_safety_lease.py::EdgeSafetyLease`
  validates and renews edge acknowledgements. The autonomous lease is 900 s,
  renewal is 300 s, and edge native Modbus freshness limit is 20 s. Physical
  bridge/connectors and HA/ESP-direct transports live under
  `runtime/physical/{connectors,transports}`; lease evidence/validation is under
  `runtime/physical/lease`. The ESPHome package remains an independent local
  owner.

## Timing and reaction boundaries

The edge's 20 s stale-Modbus rule and 900 s lease are independent hardware
containment semantics; neither is changed here. Python has distinct meanings:
the safety variable defaults include 60 s high-voltage watchdog and 300 s
watchdog (`runtime/safety/variables.py`); `managed_runtime_safety.py` uses a
60 s retry cadence only when Output is positively known ON after an
unconfirmed OFF, and a 180 s unavailable-telemetry grace; `runtime_safety.py`
also defines a 45 s orphan-output grace. These are not interchangeable stale
timers. This change makes no timer adjustment. In the opt-in MAIN Guard
transaction changed here, stale/invalid telemetry blocks the transaction
without OFF. Fresh native protection trips while Output is confirmed ON, native
Iset above the persisted Guard ceiling, native OCP above that ceiling plus
expected headroom, and failures after setter invocation request verified-OFF
containment. This is transaction-specific, not a proven invariant for all
production routes.

## D078 seam and change

Before D078, `execute_main_guard_reduction` sent every exception through the
same verified-OFF request. That included stale/skewed preflight evidence,
failed proposal validation, and failure to persist the pending snapshot, even
though no hardware setter had been invoked. D078 keeps ordinary pre-write
denials read-only, while preserving OFF containment for confirmed fresh native
protection trips with Output ON and fresh native Iset/OCP readbacks proving an
upward deviation from persisted Guard authority. Failures after setter
invocation also request OFF because the command may have reached the RD. Tests
cover stale evidence and pending-save denial, confirmed protection/Iset/OCP
fault containment before setters, and OFF after an ambiguous attempted write;
no broader production-route invariant is claimed. D061's physical OOB
Iset/OCP acceptance is recorded in
`D061_OOB_ISET_OVP_OCP_PHYSICAL_PASS_2026-10-14.md`. Those checks establish
upward setting-change detection, not electrical protection trips.

## Explicitly blocked hardware steps

- MAIN Guard initial 0.1C cap, 30-minute credible-active ratchet to observed
  current +1 A, monotonic per epoch, persistence, restart behavior and validated
  desulfation reset remain software-only. No production caller is installed;
  no Iset/OCP write enable is authorized by D078.
- MIX native register 9/17/18 evidence, heartbeat advancement, committed owner
  receipt, clipping/Delta, sticky hold and replay remain software contracts;
  never raise MIX voltage automatically. AGM behavior remains untouched.
- Do not deploy or operate managed live adoption/lease changes based on software
  tests. No ESPHome compile/flash/bench validation, HA/node action, real charging,
  output toggle, or production command is part of this work.
- Full lifecycle and exact target-node bench proof are still required before
  any actuator integration. Keep ESPHome and all hardware unchanged.
