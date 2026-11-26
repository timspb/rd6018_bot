# P1-AD086 — Runtime Safety Guard function-group owner decision
Date: 2026-11-15
Status: ACCEPTED AS FUNCTION-GROUP CONTRACT ONLY — whole file remains NO FILE-LEVEL APPROVAL; NO SAFE SLICE for source movement.

## Decision

Accept the source-backed AD085 function-group contract for runtime/safety/runtime_guard.py without moving code or changing runtime behavior.

| Function group | Existing owner | Contract |
|---|---|---|
| Parsing and evidence normalization (_finite, _binary, _OutputEvidence, _output_evidence, _is_post_command) | Safety Authority | Normalize supplied state/source/heartbeat evidence only; no acquisition or independent telemetry owner. |
| Capture/bind/install and legacy patching | Existing Safety/Physical Execution composition boundary | One production ManagedRuntimeSafetyGuard instance captures raw methods and binds the configured client; production remains patch_adapter=False. Standalone Strict/legacy patching remains a separate route. No new adapter/facade. |
| Verified OFF, _off_unconfirmed latch and direct containment | Safety Authority + Physical Execution within one guard instance | Safety owns decision/latch/verification; Physical Execution owns captured raw OFF and readback transport. One _off_lock, one existing owner. Generic guard verification is not a substitute for AD051 terminal APPLIED/R18 receipt or typed Native VerifiedOffEvidence. |
| Enable admission and verification | Safety Authority + Physical Execution; ExecutionPort is caller gate | Guard/Managed/Strict existing inheritance order owns admission and raw effect. ExecutionPort remains public app gate; SafeOutputCoordinator owns transactional enable ordering. AD072 cancellation settlement remains open. |
| V/I programming/readback | Safety Authority + Physical Execution | Safety owns bounds/live preconditions/fail-closed decision; Physical Execution owns raw setters/readback. ExecutionPort owns normal caller gates; SafeOutputCoordinator owns transaction sequence. No OVP/OCP setter. |
| Snapshot validation, envelope, orphan and telemetry state | Safety Authority; Telemetry owns source facts | Generic guard validates normalized snapshot; Managed subclass owns production managed grace/protection/temperature/foreign-output lifecycle; Strict exact-class branch remains standalone. No raw R16 consumer above typed boundary. |
| Native read-only report delegation | Telemetry/Physical read adapter; ExecutionPort owns clearance acceptance | Guard only delegates optional read-only report. No new poller/cache/authority. |

## Why no source split

The same methods interleave evidence normalization, mutable latch state, raw transport effects, post-write verification and Strict/Managed subclass behavior. The inheritance chain and private helper dispatch are production contracts. A split would require moving call ordering or adding a wrapper/facade/second owner without a demonstrated independent seam. Decision: **NO SAFE SLICE** for source movement. A stable behavioral contract is documented above; keep the file intact.

Production installation remains: production_bootstrap installs ManagedRuntimeSafetyGuard with patch_adapter=False; ExecutionPort captures that instance as its one execution owner; deferred production_runtime bind recaptures the configured client methods. Standalone Strict and legacy generic patching are not the production composition route.

## Safety exclusions

No change to the firmware single R18 writer, AD051 correlated APPLIED/FC06+FC03 receipt, 900-second lease, OVP/OCP/OPP ownership, raw R16 boundary, Safety OFF latch/retry, V/I bounds, SafeOutputCoordinator transaction, Strict/Managed inheritance, or AD072 cancellation. Do not add guard, adapter, wrapper, facade, queue, worker, lock, timer, poller, or owner. No physical, HA, ESP Native, firmware, node104 or deployment action.

## Evidence

AD085 full report: .recipe-studio-local/REPORT_MOD_P1_AD085_RUNTIME_GUARD_FUNCTION_OWNER_AUDIT_20261115_FULL.md. Source and production composition were reviewed. Tests/compile/lint were NOT RUN; no pass count or physical/firmware acceptance is claimed. No source/test/CSV/registry changes.
