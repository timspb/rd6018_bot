# RD6018 AD-145 — Manual Delta pure evidence transform and state-owner boundary

Date: 2026-11-16  
Status: **ACCEPTED — narrow source/fake refactor; physical acceptance excluded**

## Decision

Approve a narrow production-source refactor of Manual Delta evidence. AD021's test-only restriction remains authoritative for its original 2026-11-13 acceptance slice; this new AD145 explicitly authorizes the following separate source refactor while preserving every AD021/AD023 behavior.

### Ownership

- **ManualSessionManager** owns the canonical session-local evidence fields `_imin`, `_vmax`, `_delta_confirmations`, `_last_delta_confirmation`, and their reset boundaries. They remain in-memory only and remain exposed to the existing HMI projection.
- **Manual profile / Manual stop request** owns the actual threshold values: profile MIX `delta_current_a`, `delta_voltage_v`, confirmation count/interval; profile-less Manual uses the existing `request.stop.delta`.
- **Application observer** owns live-sample normalization. It already finite-checks battery voltage/current and will pass normalized regulation mode + U/I to the evaluator.
- **Manual Delta Evidence** owns only the pure evidence transition over prior state + policy + normalized sample + timestamps. It returns new evidence state and reason. It must not receive the ManualSessionManager, read its request/profile, mutate its fields, read HA, or own polling/physical execution.
- Existing constants remain in Manual Delta Evidence: 120 s blanking, 3 confirmations, 60 s spacing. Profile overrides remain exact.

## Approved implementation

In the existing `runtime/charge/evidence/manual_delta.py`:
- introduce immutable `ManualDeltaSample`, `ManualDeltaEvidenceState`, `ManualDeltaEvidencePolicy`, and `ManualDeltaEvidenceResult` values;
- change `evaluate_manual_delta_evidence` to accept those explicit inputs and return a result;
- do not import `rd6018_telemetry`, `manual_mode`, Application, or production runtime;
- retain existing evidence log messages and reason `manual_delta_confirmed`.

In the existing Application observer:
- use the already-normalized finite voltage/current and `resolve_regulation(live).value` to construct `ManualDeltaSample`;
- pass that sample to the existing ManualSessionManager `_delta_reason` adapter.

In ManualSessionManager:
- guard the existing request/MIX eligibility;
- construct policy from the existing profile/stop fields, without recomputing or changing thresholds;
- snapshot its four canonical fields into `ManualDeltaEvidenceState`;
- call the pure evaluator and copy returned state back to the same four canonical fields;
- return the existing reason unchanged.

No new production code files, manager, clock, timer, journal, persistence field, evidence epoch, task, queue, ExecutionPort or physical path.

## Exact compatibility requirements

Preserve:
- 120 s blanking inclusive at the boundary (`now - started_at == 120` evaluates);
- CV minimum-current reference `Imin`; CC maximum-voltage reference `Vmax`;
- candidate predicates: CV `current >= Imin + delta_current`; CC `voltage <= Vmax - delta_voltage`;
- reference update resets confirmations and last-confirmation timestamp;
- non-candidate resets confirmation count but retains last-confirmation timestamp;
- unknown regulation resets confirmation count but preserves reference and last-confirmation timestamp, provided the selected threshold is not None;
- missing U/I does not mutate evidence state;
- equal/backward confirmation timestamps cannot add confirmations;
- profile thresholds/count/interval override defaults exactly; profile-less uses `request.stop.delta` and defaults 3/60;
- no automatic Output ON on restart; the existing Manual session restore remains INTERRUPTED;
- start resets the Manual evidence epoch;
- cooling resets all four fields only after verified OFF and transition to COOLING;
- resume resets all four fields only after verified enable;
- failed/unverified cooling OFF preserves the evidence epoch;
- HMI continues reading the same manager fields;
- no merge with D062 adopted-MIX state/epoch.

## Validation required

- pure transform tests prove input state is immutable and returned state is the only updated state;
- full behavior parity for all existing Manual Delta contract scenarios;
- adapter tests prove the manager remains the sole field owner and the evidence evaluator has no session/request dependency;
- full 29-module Manual/Operator Pause cohort plus existing AD021/AD023 tests;
- py_compile, trailing whitespace and diff checks.

No physical charge, HA/ESP Native, firmware, OTA, service, node104 or hardware test is authorized.

## Implementation and acceptance evidence

Implemented the approved boundary:
- Added immutable ManualDeltaSample, ManualDeltaEvidenceState, ManualDeltaEvidencePolicy and ManualDeltaEvidenceResult values in the existing evidence module.
- evaluate_manual_delta_evidence now accepts explicit prior state, policy and normalized sample plus started_at/now; it returns a new state and reason. The input state is frozen and never mutated.
- The evidence module imports only logging, dataclasses and typing. It no longer imports rd6018_telemetry, manual_mode, Application, or the ManualSessionManager.
- The Application observer reuses its finite voltage/current values and resolves regulation once into ManualDeltaSample.
- ManualSessionManager._delta_reason remains the sole adapter: it selects existing profile/stop values, snapshots its four canonical fields, invokes the evaluator, and copies the returned fields back. HMI continues reading the same fields.

Validation: **281 passed, 45 subtests passed across 31 modules** covering Manual Delta contract/extraction, observer, Manual phase lifecycle, start/stop/cooling/resume/reset, session store/restart, Manual Program/profile, Operator Pause, HMI/dashboard, first-stage evidence and D072 START. py_compile PASS for all seven changed source/test files. Trailing whitespace scan: 0. Scoped git diff --check: PASS.

SHA-256:
- runtime/charge/evidence/manual_delta.py: BC2C1759E3EB5FFAB69E658AC10C514079407926A377BA74A9F79ADDAFEEE980
- manual_mode.py: BD70C2EF4BD43341C083B136A761472E652C28888C6569D5CCBD1B5BD77D8E1B
- application/manual_observer_use_case.py: BA1F3605687CB2539A913EE32C601F8E3F4FC2E8E202FB9BE465D913D45255E7
- tests/test_modularization_manual_delta_contract.py: C0A04F0200D676869B71BC164A6781BF50100DC3F74AD0459699A56E58F0F32A
- tests/test_modularization_manual_delta_extraction.py: 0CD4D445058593AF612861117531B559D8EC6268B9E4AF3EEA364BC18CC329B4
- tests/test_modularization_manual_observer_contract.py: F53144CFD82941AAE28A0E0F685EC7286C407FEBC95F2F5CCB8E557C41514E76
- tests/test_modularization_manual_observer_use_case.py: 3B21785C558E028B9775C13E60D5593C54D06BD8A3654B7E1B6703A49B9812C7

Repository: feature/main-mix-countdown-display; HEAD 3c692554074b27805419a9b0767133a1c8d78150 unchanged; staged=0; 469 total status entries. manual_mode.py is the one tracked modification in this slice; the other six paths remain untracked modularization WIP. Runtime charge/manual/pause/quarantine artifacts absent after tests. No commit/push/reset/checkout/stash/clean.

No Codex run launched because WSL Codex CLI jobs were already active in separate projects. Own-chat R7.2 route remains enabled with last_ack=null; no event/ACK claimed. node104 not queried or touched. No HA/ESP Native/firmware/OTA/service/hardware/RD6018 Output/physical charge action. 900-second Edge Safety Lease unchanged. Production/release/physical acceptance remain HOLD.

AD145 accepted as source/fake architecture only. Owner registry sidecars remain unchanged; reconcile AD142–AD145 in a deliberate later registry refresh.
