# D123 Sprint 03 evidence — P2b session identity and single writer

Date: 2026-10-19. Workspace: `/home/home-pc/rd6018-d118-start-lease-repair-20261019`.
Starting committed HEAD: `14c9140612ff156378536b13820d0c76ff763bc6`.
Interpreter: `/tmp/rd6018-d109-venv/bin/python` (Python 3.12.3).
This was source-only work: no network, GitHub, node104, ESP/HA, firmware,
service, deployment, secrets, physical commands, or package installation.

## Boundary result

- Trace ID generation and deterministic legacy restore now belong to
  `runtime.charge.session` through frozen `TraceIdentitySnapshot` values.
- Accepted restore enrichment starts from the complete existing document,
  applies canonical trace/continuation completion, and writes through the
  persistence-owned `atomic_session_write`. The controller no longer defines
  `_begin_trace_identity`, `_restore_trace_identity`,
  `_write_trace_identity_to_session_file`, or
  `_read_legacy_session_document`.
- Recovery and final SAFE_WAIT continuations retain their existing serialized
  schema and validation. Production cooling/finish/runtime-signal patch writers
  were unused and have been removed; their schema continues through the
  existing canonical session-document extension hook.
- Terminal Done normalization now uses the same atomic replacement primitive.
  MAIN Guard checkpoint revisions and SHA are protected; a document carrying
  `main_current_guard_v1` is still rejected before restore mutation or trace
  enrichment because guarded restore admission/readback reconciliation is not
  installed. Enrichment also refuses an in-memory Guard without reconciled
  checkpoint authority. Atomic I/O failure fails restore and preserves the old
  session.
- No charge thresholds, recipes, actuator logic, edge lease, OVP/OCP, MAIN Guard
  behavior, UI, ESP, or HA code was changed. Persisted state still does not
  authorize Output ON after restart.

## Verification

Focused command:

```bash
TG_TOKEN=123456789:d123-offline-sprint03 /tmp/rd6018-d109-venv/bin/python -m unittest \
  tests.test_production_controller tests.test_recovery_trace_identity \
  tests.test_final_safe_wait_output_transaction \
  tests.test_desulfation_ownership_cutover \
  tests.test_session_atomic_guard_binding tests.test_production_guardrails \
  tests.test_d123_p2b_session_writer_architecture
```

Result: **72 tests passed**.

Full offline command:

```bash
TG_TOKEN=123456789:d123-offline-sprint03 /tmp/rd6018-d109-venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Result: **2,348 tests run, 2 skipped, all others passed** in 118.847 seconds.
Captured output: `/tmp/d123-sprint03-unittest.log`. Compile and whitespace gates:

```bash
/tmp/rd6018-d109-venv/bin/python -m compileall -q .
git diff --check
```

Both exited 0. The regression suite verifies deterministic fallback identity,
existing identity restoration across legacy timer re-estimation, one canonical
enrichment write with prior keys retained, recovery/final SAFE_WAIT continuation
restore, Guard capacity/session identity checks, unchanged guarded revision/SHA,
stale Guard identity rejection, malformed `.v2.tmp` isolation, failed atomic
replacement preserving the original file, restart failure without actuator
calls, and AST rejection of controller writer/helper reintroduction.

Known prior full-suite counts remain historical and are not replaced:

- Baseline: 2,325 passed / 8 skipped.
- Sprint 01: 2,338 passed / 2 skipped.
- Sprint 02: 2,343 passed / 2 skipped.
- Sprint 03: 2,346 passed / 2 skipped.

## Scope status and next stage

P2b identity and writer convergence is complete. P2 overall remains **partial**:
stage history, broader audit/trace lifecycle ownership, and guarded restore
admission are still controller/runtime responsibilities. No new restore
authority is claimed. P3 endpoint inventory and executable preparation checks
are in `D123_P3_EXECUTABLE_CHECKLIST_20261019.md`; no P3 implementation occurred.

Current source metrics: `charge_controller.py` 2,302 LOC, 73 method
declarations / 72 unique names. Sprint 01 was 2,529 LOC, 84 / 83 after P1.
The prior Sprint 02 evidence records its intermediate 2,397 LOC, 78 / 77
snapshot; Sprint 03 removes five controller methods and the independent session
writer body.
