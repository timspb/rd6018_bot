# D123 Sprint 01 evidence — P0 + P1

Date: 2026-10-19. Worktree: `/home/home-pc/rd6018-d118-start-lease-repair-20261019`.
Baseline: `58321a866dd68195bf8264d1d9ebe7c18a60748f`; branch retained:
`codex/d118-start-lease-repair-20261019`.

This is source-only evidence. No SSH, HA, ESP Native connection, actuator or
physical command, firmware/service/deployment change, GitHub operation, package
installation/download, real secret, or production-host write occurred. The
physical node and its active session were not inspected or changed. Runtime
architecture and field inventory are in
[`D123_CONTROLLER_OWNER_MAP_20261019.md`](D123_CONTROLLER_OWNER_MAP_20261019.md).

## Executed checks

Existing WSL2 venv: `/tmp/rd6018-d109-venv/bin/python` (Python 3.12.3).
Offline test imports require a bot token-shaped environment value; all full runs
used only the synthetic local token `123456789:offline-d123-test`. No real
credential was read or used.

Baseline suite was extracted without modifying the worktree:

```bash
git archive 58321a866dd68195bf8264d1d9ebe7c18a60748f | tar -x -C /tmp/d123-baseline-58321a8
TG_TOKEN=123456789:offline-d123-test /tmp/rd6018-d109-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Baseline result: **2,325 tests passed, 8 skipped** (`/tmp/d123-baseline-unittest.log`).

Focused D123/controller/authority/restore/guard checks:

```bash
TG_TOKEN=123456789:offline-d123-test /tmp/rd6018-d109-venv/bin/python -m unittest \
  tests.test_main_sample_evidence_clock tests.test_charge_controller \
  tests.test_operator_pause tests.test_start_transaction_service \
  tests.test_charge_controller_authority tests.test_production_controller \
  tests.test_first_stage_evidence tests.test_signal_analyzer \
  tests.test_v3_main_authority_migration tests.test_main_guard_pre_on
```

Focused result: **106 tests passed**.

Full D123 source tree:

```bash
TG_TOKEN=123456789:offline-d123-test /tmp/rd6018-d109-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
/tmp/rd6018-d109-venv/bin/python -m compileall -q .
git diff --check
```

Full result: **2,338 tests passed, 2 skipped** (`/tmp/d123-final-unittest.log`).
`compileall` and `git diff --check` exited 0. The additional 13 tests versus
baseline include targeted clock/evidence contracts. The suite was run only on
Python 3.12.3; Python 3.10 and 3.11 were not installed or tested.

## P0 source inventory and boundaries

- The complete method/state owner map is
  [`D123_CONTROLLER_OWNER_MAP_20261019.md`](D123_CONTROLLER_OWNER_MAP_20261019.md).
  AST inventory: baseline 85 declarations / 84 unique names; current 84 / 83.
  Every current method name was mechanically checked against the map.
- `charge_controller.py`: baseline 2,594 LOC, current 2,529 LOC, net **-65**.
  The removed `_update_main_plateau_clock` and `_assess_main_sample` bodies were
  replaced by one typed evidence owner and one call path; no arbitrary LOC cap
  was added.
- The production route remains one existing route:
  `runtime.production_runtime:342` constructs one `ManagedChargeController`; its
  automatic runtime calls `tick` at `runtime.production_runtime:2941`. This is
  still transitional session/stage orchestration and is not declared converged.
- The historical V1 `ChargeController` FSM, `charge_logic.py` inheritance and
  historical tick/fallback, retired shadow/dual-runtime islands, compatibility
  action/UI/actuator routes remain eradicated per the ledger. Current
  `ManagedChargeController` stage/effect/session ownership remains P2–P4 debt.
- Existing modular MAIN decision remains
  `runtime.charge.strategy.main_authority.decide_main_transition`; evidence
  contains no actuation authority. Durable charge save/restore remains under
  `runtime.charge.persistence`; main-guard checkpoint writing remains under
  `runtime.charge.session_atomic`; verified physical transaction remains under
  `application.execution_port`; safety remains under `runtime.safety`; direct
  ESP Native physical truth remains in the existing `esp_direct` transport path.
- Source work did not change the current FSM count, persistence record layout,
  stage transitions, charge recipes/thresholds, OVP/OCP, thermal/telemetry
  safety, main-guard semantics, edge lease, Manual, or execution-port behavior.

## P1 call graph and state move

Before:

```text
runtime.production_runtime tick
  -> ManagedChargeController.tick
       -> _update_main_plateau_clock (mutates _v2_main_plateau_since)
       -> _assess_main_sample
       -> existing decision/stage path
```

After:

```text
runtime.production_runtime tick (same instance and route)
  -> ManagedChargeController.tick
       -> MainSampleEvidenceEvaluator.assess(MainSampleEvidenceInput)
       -> typed MainSampleEvidence.assessment
       -> existing MAIN decision/stage path
```

`runtime.charge.evidence.first_stage.MainSampleEvidenceEvaluator` owns the
restart-local plateau timestamp and first-stage calculation. START and session
resets call its `reset`; operator pause calls its `shift_clock`; existing
stage/SAFE_WAIT/cooling resets use the same owner. The former state field
`_v2_main_plateau_since` is absent from production source. The clock was never
serialized before D123 and is still empty after process restore, so restart does
not manufacture plateau evidence. The existing `ProductionChargeController`
tail-residence requirement remains a distinct policy clock and continues to
consume the typed assessment; no persistent schema or external API changed.

Parity tests cover startup with no plateau, five samples before a plateau event,
the analyzer’s existing five-sample event and exact 15-minute backdating,
`CURRENT_MINIMUM_UPDATED` reset while retaining same-sample tail assessment,
near-target and CV constraints, clock shift/reset, backward timestamp behavior,
stage exit/reentry, Ca/Ca/EFB 40-minute and AGM 120-minute thresholds, upward
thermal and downward voltage trends, and restart-empty behavior. Existing full
restore, transition, execution safety, and main-guard tests passed.

## Deferred defect and limits

The 15-minute evidence weakness is recorded separately for a later approved
algorithm decision and is intentionally unchanged. Existing
`SignalAnalyzerConfig` can emit `CURRENT_PLATEAU` after five samples spanning
12 minutes inside a 15-minute window, then the consumer backdates by the full
15 minutes. The regression `test_analyzer_five_sample_minimum_and_existing_backdating_are_preserved`
preserves this exact behavior. D123 does not alter minimum elapsed evidence.

No live ESP Native evidence was collected because the task explicitly prohibited
node/HA/ESP access. This result is not physical validation, deployment
acceptance, release readiness, or confirmation of live Output state. Exact
Python 3.10/3.11 runs and separate supervised physical acceptance remain later
gates.

## Remaining next work

- **P2:** Move trace/session observations, stage history and restore glue into
  existing evidence/session/persistence owners; preserve the guard journal and
  fail-closed restart contract.
- **P3:** Move stage/effect orchestration into existing application and typed
  stage decisions while preserving verified OFF/ON and lease transactions.
- **P4:** Remove `ManagedChargeController` as production owner only after its
  callers move to the existing application interface; do not add a facade.
- **P5:** Python 3.10/3.11/3.12 CI, exact-source release proof and separate
  supervised physical acceptance before any deployment.

Sprint state: P0 source inventory and P1 evidence cut complete locally on the
committed source SHA. D123 overall and P2–P5 remain open.
