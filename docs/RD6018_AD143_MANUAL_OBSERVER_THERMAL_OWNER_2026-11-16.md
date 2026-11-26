# RD6018 AD-143 — Manual Observer Application owner and thermal threshold ownership

Date: 2026-11-16  
Status: **APPROVED — source/fake only; no physical acceptance**

## Decision

Approve `application/manual_observer_use_case.py` as the Application owner for one-cycle Manual session orchestration.

Approve `runtime/safety/thermal_variables.py` as the sole owner of Manual external-battery thermal thresholds. The existing pause and critical thresholds are reused; the Manual cooling resume hysteresis threshold is now declared there as a typed `VariableSpec`.

## Source change

The observer previously duplicated three literals:
- 40.0 °C: enter Manual cooling;
- 35.0 °C: resume an existing Manual cooling session;
- 45.0 °C: stop the Manual session on critical battery temperature.

The repository already had canonical Safety-owned `BATTERY_TEMP_PAUSE_C` (40 °C) and `BATTERY_TEMP_CRITICAL_C` (45 °C). These are now consumed by the observer. Added `MANUAL_COOLING_RESUME_C` to the same Safety thermal owner with key `safety.thermal.manual_cooling_resume_c`, default 35 °C, CONFIG_FILE override policy and RESTART_REQUIRED change effect.

The existing observer constants `MANUAL_COOLING_PAUSE_C`, `MANUAL_COOLING_RESUME_C`, and `MANUAL_TEMP_CRITICAL_C` remain exported as float compatibility projections. Their defaults are unchanged: 40 / 35 / 45 °C.

## Application owner boundary

The observer owns only the sequencing of one Manual observation cycle:
1. reject inactive/missing-request sessions before reading;
2. read once through the existing ExecutionPort;
3. apply the existing thermal/cooling priority;
4. require finite battery voltage/current before phase/stop evidence evaluation;
5. call the existing configured stop, MAIN-tail, MIX-hold and Delta evaluators in their existing order;
6. delegate cooling, resume, MAIN→MIX and stop effects to their existing Application use cases/session methods;
7. on confirmed Delta, set the existing session finish-hold anchor and call the existing ManualSessionManager persistence owner.

It does not own the session schema/store, physical adapter, ExecutionPort, Safety guard, lease, phase lifecycle, MAIN-tail policy, Delta evidence algorithm, or supervisor polling task. The 5-second polling/supervisor remains in `application/manual_supervisor_use_case.py`; this observer is one cycle only. No direct HA access or new physical path exists.

The observer's 45 °C branch remains the existing Manual session stop workflow through the established ExecutionPort/Safety chain; it is not a replacement for ManagedRuntimeSafetyGuard's hard thermal containment.

## Regression evidence

Before change, selected baseline: **64 passed, 12 subtests** across 8 focused Manual modules.

After change, Windows project `.venv`: **144 passed, 38 subtests** across 20 modules covering:
- Manual observer and observer behavior contract;
- Manual phase evidence, lifecycle and Delta contract/extraction;
- Manual runtime/mode;
- Manual store and restart cutover;
- Manual start/stop/cooling/MIX transition/supervisor use cases;
- Operator Pause baseline/cutover/owner/use case;
- D072 Manual START ownership.

The new observer contract proves the pause/resume/critical compatibility constants are projections of the canonical Safety VariableSpecs, including exact defaults and the new resume key/owner. `py_compile` PASS for all three changed files. Scoped `git diff --check` PASS.

## Exact files

1. `runtime/safety/thermal_variables.py` — modified; add the typed Manual resume variable and export it.
2. `application/manual_observer_use_case.py` — untracked at HEAD; replace three local literals with Safety-owned values, preserve compatibility names and observer control flow.
3. `tests/test_modularization_manual_observer_contract.py` — untracked at HEAD; add the thermal variable ownership regression.

SHA-256:
- `runtime/safety/thermal_variables.py`: `7795D44164471BAD39336405C10CC58A94932106F40792FAAA6F642907F1C3BD`
- `application/manual_observer_use_case.py`: `ACCCF940D34368F998391CE514715E846671CAD372938242AB94F03E82D46120`
- `tests/test_modularization_manual_observer_contract.py`: `6E03766AA38D6930153CCA4E7279BFD9F41E750D04405D478C1DE80F4FE119B6`

## Repository and safety

- Branch: `feature/main-mix-countdown-display`
- HEAD unchanged: `3c692554074b27805419a9b0767133a1c8d78150`
- Staged: 0; no commit, push, reset, checkout, stash or clean.
- Existing WIP preserved; the two new/previously-untracked Manual paths remain untracked at HEAD.
- No Codex run was launched in this step; other WSL Codex CLI jobs were already active in separate projects. No R7.2 event or ACK is claimed.
- node104 status was not queried; node104 was not touched. No HA/ESP Native, firmware, OTA, service, hardware, RD6018 Output or physical charge action.
- 900-second Edge Safety Lease unchanged.
- Production/release/physical acceptance remain HOLD.

## Remaining Manual owner decisions

- `application/manual_phase_evidence.py`: HOLD. Its MAIN-tail helper still combines raw telemetry parsing, legacy profile-less threshold policy and delegation to the existing stateful Charge Strategy lifecycle. AD-144 must define the normalized sample/decision boundary without duplicating MAIN lifecycle state or thresholds.
- `runtime/charge/evidence/manual_delta.py`: HOLD. It evaluates CV/CC evidence but mutates ManualSessionManager-owned reference/counter fields and reads Charge Program profile thresholds. AD-145 must separate evidence algorithm from session state ownership and Charge Program policy before approving a primary owner.
- `application/operator_pause_use_case.py`: remains unapproved at file level; AD130 safety audit is not a file-owner approval.
- `application/manual_supervisor_use_case.py`: separately approved by AD142 as Application orchestration only.

Next: P1-AD144 read-only owner audit of Manual MAIN-tail evidence and the existing ManualPhaseLifecycle API; identify the smallest clean split between Telemetry normalization and ChargeEngine decision. No production edit until that boundary and parity contract are explicit.
