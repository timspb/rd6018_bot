# B1020 — P3/P8 physical acceptance preparation

Status: **PREPARATION ONLY — NOT AUTHORIZED / NOT RUN / HOLD**
Prepared: 2026-11-26
Candidate base: `775c856c14a2d4ab78e2e335a7bd6deda58c7fd2`
Branch: `codex/rd6018-b1020-hardware-acceptance-20261126`

This is an executable checklist for a separately authorized, supervised bench
session. It does not authorize touching the bench, node104, HA, ESP, or
production. The current canonical P0–P9 count remains **97/103**. P3/P8 and
release/deployment remain **HOLD**. Successful CI #2243 and ESPHome source build
#162 are source evidence only; they do not satisfy any physical row below.

## Acceptance boundary and safety policy

- A later supervised bench test requires the operator's explicit approval
  of this exact source candidate, bench scenario and intended live actions.
  This is a BENCH TEST decision, NOT the final P8 production release decision.
  Final P8 acceptance follows the physical evidence; requiring final P8
  acceptance before conducting P3 tests would create an impossible circular
  prerequisite. This document does not itself approve a test or deployment.
- No unattended hardware. An authorized operator stays at the supervised
  stand, keeps the existing emergency disconnect available, and controls every
  live action. No unattended wait for a lease expiry while output is energized.
- All actuator operations (V/I programming, Output ON/OFF, lease renew/disarm,
  and bot-controlled fault containment) use the already composed production
  bot/ExecutionPort route. Do not press ESPHome buttons, write Modbus, or issue
  direct ESP/API commands as a substitute. D091 is observation-only.
- Acquire a new direct ESP Native subscription/callback snapshot at every
  preflight and after each action. Capture `SensorState` for physical R18,
  measured voltage/current, battery voltage, Vset/Iset, raw R16, temperature,
  and the ESP-local lease/health entities. Include node identity, entity
  inventory identity, source=`esp_native_api`, native type, callback timestamp,
  subscription/acquisition time and age. The existing D091 collector accepts
  Native samples no older than 8 s; respect its current validation. Modbus age
  must be within the existing 20 s bound. HA102 is a secondary comparison only.
  TCP reachability, HA cache, UI, a button ACK, or `NumberState` is not physical
  readback.
- Preserve the final owner policy: register 82/83 OVP/OCP and R16=1/2 are
  diagnostic and explicitly operator-manageable only. They must never be used
  as automatic software or ESP protection, START/recovery/lease gate, trip,
  quarantine, or stop trigger. Do not deliberately provoke electrical OVP/OCP
  trips. Existing intrinsic RD6018 hardware functions remain enabled. R16=3
  (OPP) and unknown nonzero R16 are independent protection faults; internal
  overtemperature, measured V/I, actual R18, and the existing 900 s local lease
  remain safety authorities. ESP firmware source policy is not permission to
  flash firmware.
- For the D065 bench envelope, `tools/node104_d094_d065_bench_harness.py`
  defines a **15.5 V maximum setpoint**, 900 s lease TTL, 300 s renewal cadence,
  and 8 s evidence freshness. Keep Vset at or below 15.5 V for that scenario.
  This is a test-envelope ceiling, not a general battery charging target. For
  any battery-connected test, record battery ID, chemistry, capacity, measured
  battery voltage and the separately approved profile/target; do not choose a
  target from terminal voltage alone. If the authorized scenario does not
  explicitly require a battery, use its specified disconnected/load setup;
  historical lease-expiry bench evidence used the battery disconnected.

## Existing commands and their boundaries

Run these only in a later, separately authorized execution context. They are
listed to make the procedure repeatable; they were not invoked for B1020.

| Existing tool/path | Use in a future authorized session | Boundary |
|---|---|---|
| `tools/node104_d091_physical_proof_collector.py` | On its authorized node104 runtime, invoke with the node's configured Python (`/opt/services/rd6018-bot/venv/bin/python /opt/services/rd6018-bot/d090/node104_d091_physical_proof_collector.py`). Capture JSON stdout and stderr/exit status as an artifact before and after a phase. | Read-only OFF proof collector, not a general V/I or energized-state logger. It validates dual-source OFF, zero output V/I, direct Native typed callbacks, lease and host/service evidence. Not runnable here: fixed live node path and device access are prohibited. Do not copy secrets. |
| `tools/node104_d106_live_observer.py` and `tools/node104_d106_readonly_socket.py` | Existing observer path for authorized read-only live/phase observations where its reviewed deployment is present. Preserve its raw output and source metadata. | Read-only, not an actuator. Do not invent CLI options; use only the invocation documented in the accepted node-local observer deployment record. |
| `tools/physical_test_control_client.py` | Existing opt-in local AF_UNIX control plane; only use an operation explicitly enabled and accepted for the exact candidate. `status` is observation; `d061_verified_stop` is stop-only and only for active adopted Manual authority. | Requires `RD6018_PHYSICAL_TEST_CONTROL=1` on the running bot. Does not set V/I or enable Output. Activation itself is a separate stage and is not approved here. |
| `tools/physical_test_programming_fault_client.py` | Existing B16 one-shot `b16_fault_hold_stale_set_voltage_readback` validation, when the accepted server implementation and bench run explicitly include it. | The CURRENT physical_test_control_programmed_readback.py uses same-value Vset/Iset writes ONLY and rejects stale Vset readback before ON. OVP/OCP are not written. This is a live transaction and opt-in only; check the exact installed code and authorization first. The older B16 runbook describing four OVP/OCP/V/I writes is superseded and MUST NOT be followed. |
| `tools/physical_test_source_fault_client.py` | Existing enumerated source-freshness fault operations, only where exact candidate/runbook allows them. | In-process fault injection; not a physical R16/OPP injector and not evidence of an actual ESP fault response. |
| `tools/node104_d094_d065_bench_harness.py` | Offline contract reference for evidence fields and action invariants. | `D065Executor` only accepts `OfflineNode`; live execution is explicitly disabled. Simulator output is never physical PASS. |
| Existing bot operator START/STOP and Manual routes via the production `ExecutionPort` | Later operator-controlled V/I setpoint and Output ON/OFF checks, only after separate authorization, exact release candidate approval and fresh preflight. Record transaction trace/correlation ID and command/result. | There is no approved direct CLI command here for arbitrary V/I or Output. Do not use shell/API/ESPHome/Modbus shortcuts. If the accepted candidate/operator route cannot expose the required action or receipt, mark BLOCKED and stop; do not improvise. |

The historical B16 procedure in
`docs/assistant/B16_PROGRAMMED_READBACK_PHYSICAL_TEST.md` is stale: it describes four setter writes including OVP/OCP, contrary to the accepted V/I-only source and operator canon. Do NOT use those obsolete steps. Current B16 implementation must be independently matched to any installed test server before an authorized V/I-only validation. D065 procedure and
expected edge state transitions are in
`docs/assistant/D094_D065_BENCH_HARNESS_2026-10-17.md`;
the node-local collector boundary is in
`docs/assistant/D091_LIVE_ESP_MANAGED_EVIDENCE_2026-10-17.md`; D090 release
transaction gates are in `docs/assistant/D090_NODE104_VERSIONED_RELEASE_2026-10-17.md`.
The historical 2026-09-02 edge record is historical evidence only, not current
candidate acceptance. Its 900 s result must not be re-used to close a changed
firmware/candidate gate.

## Evidence packet to create during the future authorized run

Keep one append-only operator log plus untouched raw collector/observer output.
Use a unique run ID. Record these fields for every row; no signature, new
cryptographic gate, or digest authorization is introduced by this matrix:

- Run ID; operator and supervising witness; authorization reference; date and
  wall-clock timezone; candidate source revision and exact installed ESP
  firmware identity/version; bench wiring/load/battery configuration.
- Action name, operator route, transaction/trace ID, request timestamp,
  returned status/receipt and completion timestamp. Explicitly distinguish
  command requested/ACK from physical result.
- Before and after observations: ESP device identity; each native entity ID/key
  and native info/state type; source and callback/subscription timestamp/age;
  R18; measured V/I; battery voltage; Vset/Iset; raw R16; internal temperature;
  lease armed/generation/remaining/TTL; Modbus age; trip, boot quarantine,
  autonomous/ownership/conflict/intrinsic-fault state. Preserve HA102 values
  and timestamps separately as corroboration.
- For causal evidence, include Native connection generation and the actual
  output command receipt fields when provided: requested target, terminal
  status, observed R18, terminal completion monotonic time and connection
  generation. The post-command Native `SensorState` callback must have the
  correct identity/source, be strictly newer than command completion, satisfy
  the existing freshness bound (accepted OFF receipt <=8 s), and show the
  expected physical state. Keep pre-command samples separate from post-command
  samples.
- Raw R16 must be recorded exactly. PASS healthy baseline only for R16=0.
  R16=1/2 remain observed diagnostics and must not cause automatic trip/stop;
  do not intentionally cause those electrical conditions. R16=3 and unknown
  nonzero must enter the exact approved isolated fault-test path and produce
  the expected safety containment plus fresh verified OFF. If no safe existing
  physical stimulus is available, record BLOCKED; do not synthesize a hardware
  fault.
- Lease test: record the configured TTL (900 s), starting and ending generation,
  armed/remaining/tripped/quarantine state, direct Modbus age and actual R18.
  For an authorized expiry test, use only the established supervised scenario;
  operator controls the stand throughout. The test must show the ESP-local OFF
  action at expiry and fresh post-event Native R18 plus measured zero V/I. A
  simulator, elapsed-time guess, stale sample, or old D065 report cannot pass.
- Preserve all failures, timeouts, cancellations and ambiguous ACKs unchanged;
  include exact error/log output and last confirmed state. Never retry an
  ambiguous physical action automatically.

## Executable checklist and deterministic decisions

For every row, mark exactly one: **PASS**, **FAIL**, or **BLOCKED**. Do not mark
PASS from source tests, CI, command ACK alone, historical evidence, or a
simulator. Any FAIL, stale/missing/mistyped Native value, identity mismatch,
unexpected R18 ON, nonzero post-OFF V/I, invalid lease state, ambiguous action,
or missing receipt stops the matrix. Invoke only the existing supervised
safe-OFF route appropriate to current ownership; obtain a fresh direct Native
post-OFF proof. If state or command execution is uncertain, stop all further
actions and preserve evidence.

### Gate 0 — authorization, bench and candidate identity

- [ ] Operator explicitly authorizes the exact candidate, supervised bench
  scenario and any intended energized/fault action. No new signature or
  identity-verification system is required.
- [ ] Source candidate and existing bench safety prerequisites are reviewed.
  Final P8 release acceptance is NOT required before these P3 tests; it follows
  the results. Production installation remains prohibited.
- [ ] Exact candidate/firmware identity is recorded; no unapproved firmware
  build/flash or node104 deployment is planned.
- [ ] Supervised operator, emergency disconnect and approved load/battery
  scenario are present. All operators agree no unattended action is allowed.
- [ ] D090/D091 read-only evidence path is available under its approved host
  boundary. If unavailable: `ESP ACCESS BLOCKED`, stop; do not substitute HA.

**PASS:** all items have documentary evidence before touching equipment.
Otherwise **BLOCKED**; no bench action.

### Gate 1 — direct Native baseline and OFF invariant

1. Use the approved D091 read-only collector/observer on the authorized host.
2. Confirm ESP identity and fresh typed callbacks. Record Native R18, measured
   output V/I, battery voltage, Vset/Iset, R16, temperature, lease, trip,
   quarantine and ownership. Capture independent HA comparison.
3. Require R18=OFF and measured output V=0 and I=0 in fresh Native and
   corroborating HA observations; lease/edge state must match the specific
   test's approved precondition. Check no active session/ownership conflict.

**PASS:** all identity, type, source, age and values are present and consistent.
Otherwise **FAIL/BLOCKED**, no actuator action. A setpoint `NumberState` never
substitutes for measured `SensorState`.

### Gate 2 — V/I programming plus independent Native readback (P3)

1. Record approved baseline Vset/Iset, OVP/OCP telemetry and measured battery
   voltage. Select only the approved scenario's values. For D065 use Vset <=
   15.5 V; never infer a battery target from battery voltage alone.
2. Through the existing authorized operator action and production
   `SafeOutputCoordinator`/ExecutionPort, issue one bounded programming/start
   transaction. Do not create an arbitrary direct command. Capture the complete
   transaction trace and each programming/readback stage.
3. Require Vset and Iset readback from newly received direct ESP Native typed
   callbacks after the writes, distinguish them from measured V/I. Capture
   corresponding independent HA values/timestamps. Require exact requested
   values within the production readback tolerance recorded by that transaction.
4. If the authorized plan includes B16 stale-readback fault validation, use
   only the existing `physical_test_programming_fault_client.py` operation.
   Expected: `telemetry_invalid`/programmed-readback failure before any ON
   attempt, `output_on_attempts=0`, then real Vset heartbeat becomes fresh
   after injection removal. Current B16 must perform exactly one same-value
   Vset and Iset write, zero OVP/OCP writes, zero ON attempts, and confirm
   unchanged observed settings, R18 OFF and lease unarmed/remaining zero.
   Any version implementing OVP/OCP writes is NOT approved for this gate.

**PASS:** all programmed values independently read back after transaction,
Native identity/freshness is valid, event/action/readback trace is causally
linked, and final state matches scenario. For B16, all listed negative-path
assertions also hold. Missing exact live setpoint path/receipt: **BLOCKED**.
Mismatch, unexpected ON, or failure to verify OFF: **FAIL** and stop.

### Gate 3 — Output ON/OFF and Native receipt causality (P3)

This row requires a separately approved, supervised energized scenario and an
approved safe load/battery arrangement. An OFF-only test does not satisfy ON.

1. Fresh direct Native preflight immediately before the existing bot START:
   identity/currentness valid, R18 OFF, measured output V/I zero, R16=0,
   temperature acceptable, lease/ownership/session state valid, approved
   battery voltage/profile/limits in range, and exact Vset/Iset already
   confirmed. Capture trace ID and pre-command callback timestamps.
2. Issue exactly one START through the existing production operator route.
   Record request, ACK, transaction receipt, lease generation/armed/positive
   remaining, and the first post-command Native SensorState callbacks.
3. **PASS ON:** receipt/transaction is applied; callback is from same expected
   ESP identity and Native source, newer than command completion, fresh under
   the accepted signal bound; R18=ON; measured V/I are plausible for the
   approved scenario and agree with independent HA within existing tolerance;
   lease and safety flags are valid; evidence IDs link preflight -> command ->
   post-readback. ACK without this readback is not PASS.
4. Issue exactly one existing bot STOP. Record receipt separately from
   observation. Require a fresh post-completion Native R18 `SensorState` with
   R18=OFF and actual measured V=0/I=0; callback timestamp strictly newer than
   command completion and <=8 s under the accepted OFF receipt rule. Capture
   connection generation and output receipt identity. Compare independent HA
   after it updates; conflict blocks acceptance.

**PASS:** both ON and STOP phases pass with causally linked fresh direct Native
readback. **FAIL:** any mismatched receipt, stale/old callback, nonzero OFF
measurement, unexpected transition or HA conflict. **BLOCKED:** no approved
energized scenario/route or inability to acquire Native callback. Use only the
existing verified-OFF containment after any failure; do not issue a second ON.

### Gate 4 — R18 / raw OPP / unknown R16 / lease physical fault gate (P3)

Execute only exact-source fault cases explicitly covered by the approved
candidate runbook. Separate each case; re-establish fresh verified OFF and
approved starting state before proceeding. Do not make manual direct R16 or
lease writes.

| Case | Stimulus | Required observed result | Decision |
|---|---|---|---|
| R18 actual output and OFF containment | Approved production ON then bot STOP or the approved fault-containment event | Fresh Native R18 reports actual state; after STOP require post-completion R18 OFF and measured 0 V/0 A | PASS only with causal fresh Native proof |
| R16=3 OPP | Only an approved, existing isolated bench stimulus; never provoke on a battery | Raw Native R16=3 is recorded; approved safety path drives/keeps Output OFF, lease/session containment as specified; fresh R18 OFF and zero V/I follow | FAIL if no expected containment; BLOCKED if no approved safe stimulus |
| Unknown nonzero R16 | Only an approved exact-source test stimulus | Exact raw value recorded; fail-closed protection containment; fresh OFF + zero V/I | Same as R16=3 |
| R16=1/2 and OVP/OCP | Observation only; no deliberate electrical trip | Record raw 1/2 and registers 82/83 if naturally present; prove these values do not cause new automatic software/ESP stop, trip, quarantine or lease gate. No charge-admission dependence. Do not provoke OVP/OCP. | Any automatic OVP/OCP/R16=1/2 stop is policy FAIL and stop; absent natural observation is not a required stimulus |
| Internal overtemperature | Only approved existing exact-source safe fault test; no unsafe heating | Existing thermal protection response and verified OFF, using fresh Native state | BLOCKED if no safe existing stimulus; never heat device to create fault |
| 900 s local ESP lease expiry | Existing approved supervised lease bench scenario, operator continuously present | TTL=900 s unchanged; lease expires locally without renewal; actual R18 becomes OFF, measured V/I zero, tripped/remaining/armed/generation match firmware contract; fresh Native callbacks prove event and no bot/HA dependency for terminal OFF | PASS only on physical event/readback; no simulated clock or old report |
| Lease renew/disarm transition (if required by exact candidate) | Existing operator/bot route from verified OFF | Renew: armed=true, positive remaining, generation exactly +1, R18/zero V/I unchanged. Disarm: armed=false, remaining=0, no autonomous conflict; current lambda may leave generation unchanged | Use D094 expected transitions; mismatch/stale ack FAIL |

Lease-expiry energized testing is a distinct approved test and must not be
combined with an unattended wait or inferred from D094's offline model. If the
approved D061/D065 firmware/fault stimulus is not available, document
**BLOCKED—physical stimulus/tool unavailable**; do not implement an improvised
fault injection.

### Gate 5 — bounded operator control and clean exit

- [ ] Every action is operator initiated, one at a time, with no scheduler,
  automatic retry, or unattended control loop added for this test.
- [ ] Operator can issue the established STOP/safe-OFF action through the
  authorized owner and observe its receipt. Emergency disconnect remains
  available as the existing physical contingency.
- [ ] After every OFF-only step, fresh Native R18=OFF and measured V/I=0 are
  captured; after the final step lease state, ownership and session cleanup
  match the approved exit state. No unexpected setpoint/protection change.
- [ ] Physical-test opt-in/socket (if separately activated) is disabled and
  removed after the run by its authorized operator; capture that cleanup.
- [ ] Preserve raw logs, errors and all three-way outcomes. No ambiguous action
  is retried; any unresolved state stays failed/blocked.

**PASS:** complete evidence packet and every required row PASS, no unresolved
ambiguity, and verified physical OFF. This closes only the reviewed physical
subgate after owner acceptance; it does not itself authorize deployment.

## P8 release and node104 decision — separate gates

P8 physical acceptance is a distinct release decision after P3 evidence is
collected. P8 requires the owner to review the exact candidate and packet,
resolve every applicable firmware/source pairing requirement, record
PASS/FAIL/BLOCKED, and explicitly accept or reject release. No B1020 report,
CI result, old D090/D091/D065 report, or collector run alone can do this.

Node104 deployment is a later, separate decision and is not implied by P8
physical PASS. Only after release acceptance may the owner consider a separately
authorized deployment under `docs/DEPLOYMENT.md` and the existing D090
transaction procedures. The D090 physical pre/post proofs must be newly
collected at their required transaction phases; pre-stop evidence cannot be
reused as post-stop proof. If release acceptance is absent or any physical gate
is failed/blocked, node104 remains untouched and deployment remains HOLD.

## Owner closeout fields (leave open until actual evidence exists)

- P3 physical V/I, ON/OFF, Native receipt causality: **OPEN / HOLD**
- P3 R18/OPP/unknown R16/lease physical fault gate: **OPEN / HOLD**
- P3 equipment prohibition before authorization/release gate: **ACTIVE**
- P8 separately authorized physical acceptance: **OPEN / HOLD**
- P8 post-release node104 deployment consideration: **NOT AUTHORIZED / HOLD**
- P0–P9: **97/103; no checkbox changed by this preparation**
- Owner decision, evidence packet location, unresolved rows, and any next
  separately scoped authorization: ______________________________
