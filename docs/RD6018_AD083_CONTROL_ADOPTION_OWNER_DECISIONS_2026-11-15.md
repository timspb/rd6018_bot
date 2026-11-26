# P1-AD083 — Control mode and adoption owner decisions
Date: 2026-11-15
Status: HISTORICAL AD083 DECISION; function-scope disposition superseded by B902 (2026-11-25). No file-level approval is granted.


## B902 current function-scope disposition (2026-11-25)

B900 contained a stale AD083 claim that `_verified_off` ignored false OFF results. Independent inspection of the exact B900 source at lines 364–398 and the current focused regressions confirms that behavior is already contained. B902 accepts the actual bounded D061 scopes below; this does not approve `rd_managed_adoption.py` as a whole.

- Application transaction orchestration: `adopt`, `recover_startup`, and `verified_stop` coordinate the existing D061 operation and state transitions.
- Recovery & Ownership: the D061 adoption identity/state record, `_document`, `_persist`, `_restore`, and adoption lifecycle state remain capability-specific; durable HANDS_OFF/PB_MANAGED ownership remains with `rd_control_mode.py`.
- Safety admission: `_preflight_live`, fingerprint checks, authority conflict checks, and OFF_PENDING containment determine whether D061 can proceed using existing evidence and policy.
- Manual session lifecycle: `_prime_manual_authority` and `_retire_manual_software` coordinate the existing ManualSessionManager; Manual persistence/state remains owned by that manager.
- Physical OFF: `_verified_off` delegates to the existing ExecutionPort or existing HANDS_OFF owner. False return and ordinary exception persist OFF_PENDING and return False before lease disarm or Manual retirement; `CancelledError` propagates; only a true result proceeds to disarm/retirement. No second physical path is introduced.
- Telegram callbacks remain transport/workflow adapters. D062 MIX state, evidence, timing and decisions remain exclusively in `rd_managed_mix.py`; no D062 authority is assigned here.

Focused fake-only evidence: `tests.test_rd_managed_adoption`, `tests.test_rd_managed_mix_adoption`, and `tests.test_output_off_containment` **37/37 PASS** under the specified isolated environment. This closes the AD083 functional HOLD while preserving the whole-file exclusion.

## Historical decisions (the false-return finding below is superseded by B902)

| Module | Primary owner | Decision and exclusions |
|---|---|---|
| rd_control_mode.py | Recovery & Ownership | APPROVED WITH NARROW EXCLUSION. Durable PB_MANAGED/HANDS_OFF mode state, transition lock and ownership release lifecycle. Exclude direct Safety OFF call in operator_output_off until the existing ExecutionPort explicit HANDS_OFF OFF exception is defined. UI/installer wrappers are presentation/composition, not authority. |
| rd_live_adoption.py | Recovery & Ownership | APPROVED WITH NARROW EXCLUSION. Distinct HANDS_OFF external-Mix observer, evidence epoch and OFF_PENDING recovery record. Exclude Telegram/dashboard composition and terminal OFF's reliance on the direct manager Safety path until the shared ExecutionPort OFF contract is resolved. |
| rd_managed_mix_adoption.py | Presentation / Telegram workflow | APPROVED WITH NARROW EXCLUSION. HMI projection, callback routing and confirmations. D062 state/identity/clock/budget/decision remains solely in rd_managed_mix.py; runtime Safety hook installation is a composition seam, not Presentation authority. |
| edge_live_adoption.py | Recovery & Ownership | APPROVED WITH NARROW EXCLUSION. D061 edge live-adoption handshake and admission/recovery transaction. Existing EdgeSafetyLease owns lease state/renewal clock and firmware owns physical lease. Exclude dynamic renew_if_due method replacement and private lease/_press access pending a narrow interface contract. No second lease manager or renewal loop. |
| rd_managed_adoption.py | NO FILE-LEVEL APPROVAL | Mixed Application transaction order, Recovery & Ownership identity/recovery record, Safety admission, ManualSessionManager persistence/lifecycle, ExecutionPort effects and Telegram callbacks. Its _verified_off ignores boolean OFF results, then retires Manual state and reports “Output verified OFF”. Resolve false-return containment before any whole-file approval. |

## Required boundaries retained

- AD051 remains the sole firmware R18 Output writer. D061/D062 edge adoption changes lease ownership around an already-ON Output; it does not write R18 or program V/I.
- HANDS_OFF and PB_MANAGED are durable mode ownership states; Manual session JSON remains with the existing Manual store; quarantine RAM/journal remain with AD073 owners; D061 and D062 adoption documents remain capability-specific records, not canonical session or OFF evidence.
- The existing EdgeSafetyLease remains the one Python renewal owner and the firmware lease remains the physical deadline owner. No new timer, poller, lease manager, worker, lock, token, state store or cryptographic authorization.
- The direct explicit HANDS_OFF OFF path currently calls ManagedRuntimeSafetyGuard directly, bypassing ExecutionPort's mode/startup/quarantine policy, audit envelope and normal owner lock. This is an integration boundary defect, not a second physical writer. A shared OFF exception must be designed against the existing port and its single Safety/physical owner; do not add a parallel route.
- D061 _verified_off currently ignores bool results from operator_output_off, request_emergency_off and request_verified_off; a false result without exception can still retire Manual software state and claim verified OFF. This is not accepted. No file-level approval for rd_managed_adoption.py.
- AD072 START cancellation settlement remains separately OPEN. These adoption decisions do not prove a canceled sent-ON is fenced by a terminal same-owner OFF APPLIED receipt.

## Evidence and limits

Independent source review of the complete AD079 report and affected source paths confirms the owner map and two defects. AD079 tests were NOT RUN; no pass count or physical/Native/lease proof is claimed. Relevant tests inspected by AD079 include test_rd_control_mode.py, test_rd_live_adoption.py, test_rd_managed_adoption.py, test_rd_managed_mix_adoption.py, test_edge_live_adoption.py, test_execution_port_policy_boundary.py, test_guard_execution_owner_lock.py, test_rd6018_output_owner_contract.py, test_esp_output_command_receipt.py, test_hass_safe_output_gate.py, test_session_recovery_guard.py, test_main_guard_transaction.py, test_managed_runtime_safety.py, test_rd_hands_off_transfer_barrier.py and test_rd_managed_mix_hardening.py. Not run in this decision.

No source/test/CSV/registry/generated changes. No node104, HA, ESP Native, network, hardware, firmware/OTA, service restart or deployment. Release remains HOLD.
