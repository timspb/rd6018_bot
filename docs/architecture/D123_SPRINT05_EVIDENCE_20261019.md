# D123 Sprint 05 — P2d trace capture and diagnostic lifecycle

Date: 2026-10-19  
Base: `ecf93350a553d3b342535b202bb4442a6e216169` (D123 Sprint 04)  
Scope: offline source-only work in the existing WSL2 Ubuntu 24.04 checkout.
No node, ESP, HA, SSH, GitHub, firmware, service, deployment, secrets, package
installation, or physical operation was used. This report is not physical
acceptance and grants no authorization.

## Ownership cut

- Added frozen `RecoveryTraceContext` and its volatile deterministic fallback
  construction to `runtime.charge.evidence.trace_context`. The existing
  `ManagedChargeController.recovery_trace_context` dict interface remains for
  migration callers, including `application/start_transaction_service.py`.
  Session ID format, six-decimal timestamp seed, timestamp value, intent and
  condition enum objects remain the same.
- Moved disagreement state, reset, warning formatting and the exact first /
  every-twentieth repeat throttle into `TraceLifecycle` in the evidence owner.
  Removed controller `_log_shadow_disagreement`, `_v2_last_disagreement`, and
  `_v2_disagreement_repeat_count`.
- Moved capture admission (database readiness, mapping trace point, non-idle
  stage, positive start time) to `recovery_trace_store.capture_shadow_trace_if_ready`.
  The existing `record_shadow_trace` remains the only database insert owner.
  Evidence imports no database module; capture failure stays a diagnostic
  persistence error and does not revise an already formed action dictionary.
- Deleted controller `_persist_shadow_trace_if_ready`; the existing tick now
  makes one capture-owner integration call. Trace point/shadow payload assembly
  and DB schema are unchanged. No charge-session writer or service runner was
  added.
- The signal analyzer snapshot remains an observational, read-only diagnostic;
  an AST test rejects output-enabling/setter calls in its body. MAIN Guard
  restore admission and remaining audit/session lifecycle work remain pending,
  so **P2 is still partial**.

## Regression and verification

Focused set:

```text
31 tests: PASS
```

It covers trace row/session metadata and shadow payload parity, sample count and
replay, deterministic restart identity, unavailable-database capture, failure
isolation, enum/timestamp/session-ID fallback, frozen context/read inputs,
disagreement throttling, single-writer AST guard, diagnostic-only snapshot, and
architecture import constraints.

Final complete discovery, Python 3.12, using only the synthetic token
`TG_TOKEN=123456789:d123-sprint05`:

```text
Ran 2355 tests in 121.580s
OK (skipped=2)
```

That is **2,353 passed / 2 skipped**. `python -m compileall -q .`, the focused
suite, architecture import checks and `git diff --check` passed. Full-suite log:
`/tmp/d123-sprint05-final-unittest.log`.

## P3 decision

P3 was not started. The next bounded task is specified in
`D123_P3_EXECUTABLE_CHECKLIST_20261019.md`: move only the existing
`AuthorityAction.ENTER_DESULFATION` effect application into the existing
application/charge orchestration while preserving the exact action keys and
values, resets, stage state, and single `application.execution_port` verified
transaction. It requires action/state parity, writer-count, transaction failure
and restart tests before implementation. No plateau algorithm change was made;
the five-sample / 12-minute plateau weakness remains deferred as before.

## Safety and status

The source changes do not modify 900s edge lease behavior, guard, OVP/OCP,
recipes, charge thresholds, algorithms or persisted session schema. Controller
stage/effect ownership remains transitional. The only durable write relevant to
this cut is the existing recovery trace store insert; this does not add a charge
session writer. Production remains separately governed by its deployed D122
commit and requires its normal independent Native evidence and physical
acceptance process before any future deployment.
