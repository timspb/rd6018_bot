# RD6018 AD-003 — PHYSICAL COMMAND OWNER TRANSITION (2026-11-12)
**ГЛАВНАЯ ЗАДАЧА: ПОЛНАЯ ДЕКОМПОЗИЦИЯ И МОДУЛЬНОСТЬ. CHATGPT — АРХИТЕКТОР И ПРИЁМЩИК. LUNA — РУКИ.**

## Verified source evidence (P3-0)
- Audit report: .recipe-studio-local/REPORT_MOD_P3_0_PHYSICAL_CHAIN_20261112.txt. Static-source evidence only, no actual node104 hardware proof.
- bot.py ProductionComposition.compose installs production ExecutionPort and ManagedRuntimeSafetyGuard, then RD control mode, managed-live adoption, managed-MIX adoption. The later wrappers capture and delegate to previously installed functions. They implement distinct authorization and safety decisions; do NOT remove any wrappers before behavioral parity is proved.
- runtime physical binding resolves selected ESP Native or HA adapter. Its actual node104 selected connector is not verified in this audit.
- application/execution_port.py apply_intent sets I then V; program_voltage_current sets V then I. These are distinct observable transactions. Do not arbitrarily standardize order without architecture decision, prevalidation and parity tests.
- HassClient.turn_on has programming/freshness/preflight/readback/rollback safeguards. OFF acknowledgement from register 18 readback is not the same as a newly timestamped ESP Native callback evidence receipt; neither alone proves zero measured V/I.
- OPP raw R16=3 fault; 1/2 neutral. Missing and unknown handled as independent fail-closed conditions. Preserve 900s deadman and 72-hour fuse, verified OFF, hardware ESP safeguards.
- Lower-level setter/Output methods are independently callable; their reachability outside ExecutionPort and real wrapper coverage remain unproven.

## Architect decision
1. Physical execution owner: use EXISTING ExecutionPort + configured HassClient/connector transaction path; simplify code only after existing wrapper semantics are proven. No new bus, service, dispatcher, framework, or second actor.
2. Safety policy and physical transport are distinct responsibilities. Keep wrappers until a narrowly defined equivalent guard is established. The production command chain must have one authorized owner, not one global class that performs every duty.
3. P3-1A FIRST: build non-actuating regression parity tests against existing APIs and fake owner/backends; no runtime/firmware/config changes. Assertions must reflect existing confirmed behavior and exact guarantee, not invented stronger proof.
4. Preserve I->V and V->I distinct paths as baseline. Architect will decide whether and how to unify after test evidence. Failed safety case is not silently waived.
5. Test codes 1,2,3,missing,unknown with canonical resolver; test strict post-OFF Native evidence freshness independently; test existing pair call ordering and denied operations before physical ON.
6. After parity, P3-1B may isolate only one source-level physical contract function at a time while retaining façade and all production call paths. Re-run focused and OS-appropriate regression.

## Required evidence
- No HA/ESP/node104/SSH/physical actions, no Output ON and no service restart in P3-1A.
- Windows venv and Linux dependency-light tests, explicit PASS/FAIL, git diff --check, exact changed-file allowlist. No git add/reset/commit/push.
- Update docs/RD6018_MODULARIZATION_MASTER_PLAN_2026-11-12.md and docs/assistant/RD6018_CURRENT_CHECKPOINT.md only after ChatGPT independently accepts results.
