# P1-AD092 — Telemetry and signal diagnostics owner decision
Date: 2026-11-15
Status: ACCEPTED — NO SOURCE CHANGE.

## Decision

Accept .recipe-studio-local/REPORT_MOD_P1_AD075_TELEMETRY_SIGNAL_DIAGNOSTICS_AUDIT_20261115.md as the current-worktree source audit. No source/test changes, no tests run, no physical/network/HA/ESP Native/firmware actions.

Preserve these owners:
- runtime/charge/diagnostics.py: application diagnostic context orchestration and read-model/risk analysis, with timer/AI stage snapshots remaining presentation/read-model outputs; do not promote the entire file into a single canonical timer owner.
- runtime/telemetry/recorder.py: minimal in-memory TelemetryRecorder contract/test adapter. It is not production-wired and must not be turned into a second observer, poller, durable store or worker without a concrete existing consumer requirement.
- signal_analyzer.py: shared signal interpretation over caller-supplied timestamped samples; no transition or Safety authority.
- recovery_session.py: recovery trace identity/aggregation and restart evidence, consuming SignalAnalyzer but not taking over its interpretation contract.
- recovery_trace_report.py: offline/read-only recovery trace report builder.
- charging_log.py: existing append-only operator event log, distinct from canonical session JSON, recovery trace DB, quarantine journal and temperature provenance journal.

No whole-file moves for mixed-function modules. Diagnostics and recovery session approvals are explicitly narrow by function group. Preserve AD062 plateau observer/policy, AD064 MAIN Guard text boundary, AD065 MAIN authority, first-stage evidence, trace-context and temperature-source journal boundaries. Keep critical freshness and telemetry recovery in existing Safety modules.

## Explicit evidence limits

The report establishes source call graphs and ownership, not live source freshness or physical provenance. SignalAnalyzer and RecoverySession consume caller-supplied values/timestamps; test fixtures/replay do not prove Native callback freshness. Generic TelemetryRecorder is not production-bound in inspected graph, but this is not a defect requiring a new binding. No tests were run. No physical data was collected.

## Next work

No follow-up implementation is authorized or needed for AD075. Continue AD091, the single outstanding START_PENDING restart-admission contract blocker. Do not add a recorder/observer/poller/queue/store.
