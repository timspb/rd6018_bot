# P1-AD078 — Telemetry, signal and diagnostics owner decisions
Date: 2026-11-15
Status: SIX HIGH-RISK FILE OWNERS ACCEPTED WITH BOUNDED SCOPE; no code movement.

## Whole-file decisions

| Module | Decision | Existing owner |
|---|---|---|
| runtime/charge/diagnostics.py | APPROVE WITH NARROW EXCLUSION | Application |
| runtime/telemetry/recorder.py | APPROVE AS-IS | Telemetry |
| signal_analyzer.py | APPROVE AS-IS | Engine / Charge Stages |
| recovery_trace_report.py | APPROVE AS-IS | Recovery & Ownership |
| recovery_session.py | APPROVE WITH NARROW EXCLUSION | Recovery & Ownership |
| charging_log.py | APPROVE WITH NARROW EXCLUSION | Sessions & Persistence |

No source moves, new modules, second observers or new recorders are approved.

## Function-group decisions and boundaries

### runtime/charge/diagnostics.py — Application
The module is a legacy diagnostic assessment/read-model façade over compatibility-shaped controller state. Its cohesive Application groups are:
- diagnostic context initialization/update and stored specific-gravity refresh;
- supplied-sample bank-health/advisory risk and post-charge relaxation heuristics;
- timer/hold/AI stage/temperature-compensation snapshots and formatting.

**Narrow exclusion:** battery-fault classification and the automatic-HV block verdict remain with the existing battery_fault_engine / Safety Authority. diagnostic_hv_veto is only the Application adapter that converts an existing DiagnosticAuthority result into the existing AuthorityDecision veto. Application must not redefine the battery-fault classes, HV admission or raw telemetry provenance. The module does not acquire ESP Native/HA samples, validate freshness, persist canonical state or actuate Output. Bank-risk and post-charge heuristics remain advisory, not MAIN/MIX or accepted recovery-plateau policy. No new config module is justified by this owner decision; existing local heuristic constants remain owned here until a concrete configuration change is authorized.

Exact production path: application/charge_session_tick.py:27,56-60 refreshes stored diagnostics; application/charge_stage_tick.py:14-15,27-34,48-53 updates diagnostic evidence and applies the existing HV veto; operator snapshots call controller get_timers/get_ai_stage_snapshot through application/operator_snapshot_provider.py:126,368-373,436,534 and the existing controller facade. No direct hardware path.

### runtime/telemetry/recorder.py — Telemetry
TelemetryRecorder is a minimal typed interface; InMemoryTelemetryRecorder is a small in-memory list adapter. It owns neither sample acquisition, freshness, provenance, durable storage nor a poller. Source search found no production construction/call of this interface; treat it as an unused contract/test adapter, not as the active telemetry recorder. No additional production observer or recorder is authorized.

### signal_analyzer.py — Engine / Charge Stages
The SignalAnalyzer is the existing deterministic signal-evidence interpreter: sample validity, rate/window calculations, CV Imin/delta-I and CC Vmax/delta-V, confirmation counters, trend/plateau metrics and events. It is pure relative to supplied samples and caller-provided timestamps; its bounded deque and clocks are per-instance. It does not acquire telemetry, prove source identity/freshness, select stage transitions, program targets or actuate hardware.

**Department mapping correction:** "Signal/Evidence" in AD075 is a functional description, not a new department. The existing primary department is Engine / Charge Stages for the stage-specific CV/CC signal evidence. Telemetry remains the owner of acquisition, typed snapshots, freshness, epoch and provenance. Existing Recovery & Ownership consumers may own their per-session analyzer instance but do not become a second algorithm owner.

### recovery_session.py — Recovery & Ownership
RecoveryTracePoint, RecoverySessionTracker and replay helpers own explicit recovery-cycle trace identity and derived evidence aggregation from caller-supplied points. The tracker may own one SignalAnalyzer instance for its trace segment; this is composition, not a duplicate analyzer. It does not own live charge transitions, accepted recovery plateau observer/policy, current process ownership, durable session persistence or Output.

**Narrow exclusion:** keep AD062 recovery plateau observation/policy in its accepted modules. RecoverySessionTracker remains trace/replay evidence only.

### recovery_trace_report.py — Recovery & Ownership
The module owns read-only analysis/reporting over persisted recovery trace rows and captured shadow mappings. Report metrics, distributions and nominal Mix budgets are calibration/report projections only. build_trace_report initializes/opens the existing trace store before SELECT; schema lifecycle remains with recovery_trace_store / existing persistence owner. It does not observe live samples, write trace rows, choose stage, or actuate Output. The only discovered entrypoint is recovery_trace_export.py; no production charge-tick caller.

### charging_log.py — Sessions & Persistence
The module owns the human-readable operator event-log adapter, formatting, current-session text projection and scheduled retention/rotation. It is not canonical charge_session.json persistence, typed telemetry recording, recovery trace DB, or physical OFF proof.

**Narrow exclusion:** implementation is not strictly append-only: trim rewrites the file, rotation moves/recreates it and deletes older archives. It also has a process-global logger and fixed import-time LOG_FILE path; archive discovery uses current working directory even when RD6018_STATE_DIR points elsewhere. These are existing implementation constraints to keep visible, not a reason for a speculative new logging service.

Correction to AD075 call graph: trim_log_older_than_days and rotate_if_needed do have direct scheduled production callers at runtime/production_runtime.py:1379-1380. The module is imported at :73; get_recent_events is wired at :719,1476,1748; application/journal_read_service.py:17-19 reads current/recent entries; operator_managed_stop.py:17,218 records the caller's already-verified stop event. log_verified_auto_stop itself does not verify Output and must not be treated as physical evidence.

## Accepted-decision reconciliation

- AD062 plateau observer/policy remain unchanged. SignalAnalyzer generic plateau metrics, diagnostics post-charge heuristics and RecoverySessionTracker aggregation do not replace the accepted plateau owner pair.
- AD064 raw protection/R16 representation stays behind the typed MAIN Guard diagnostic boundary. This audit does not authorize raw R16 in diagnostics or trace output.
- AD065 MAIN transition choice remains runtime/charge/strategy/main_authority.py. The diagnostics HV veto is a separate existing safety veto; none of these six modules becomes stage-transition authority.
- AD071/AD073/AD076 session, recovery, START and persistence boundaries remain unchanged.

## Test evidence and limitations

AD075 inspected the exact test inventory in .recipe-studio-local/REPORT_MOD_P1_AD075_TELEMETRY_SIGNAL_DIAGNOSTICS_AUDIT_20261115.md. Every test was **NOT RUN** in this decision. Existing tests cover analyzer synthetic trajectories, MAIN Imin clocks, recovery replay/trace reporting, diagnostic state/veto, and file-backed charging-log formatting. They do not prove live Native provenance/freshness, physical Output, recovery plateau policy equivalence, concurrent log writes or deployed state-dir rotation behavior. No focused production consumer exists for TelemetryRecorder.

No pass count is claimed. No source/test/doc/CSV/registry/firmware/HA/ESP Native/hardware/node104/deployment changes.

## Cumulative P1 census

AD078 adds six primary/effective owner decisions: 44 primary / 65 effective / 434 pending. High-risk: 30 approved / 12 explicitly unapproved / 31 blank-pending; critical remains 15/15. These are manual cumulative source-decision counts from AD061 baseline plus accepted AD062–AD078 decisions, not a live count from the stale AD014 sidecar or AD012 generated CSV. Those historical files are not rewritten.

## Audit correction and provenance

AD075 report was produced in the retry run using workspace-write restricted to the exact report file; no other write was permitted. Independent source check confirms the production maintenance calls at runtime/production_runtime.py:1379-1380, so the report's earlier "no direct production caller" wording for trim/rotate is corrected here. The report's phrase "Signal/Evidence" is mapped to the existing Engine / Charge Stages department; no new department is created.

AD075 was report-only; tests NOT RUN. Branch/HEAD remain feature/main-mix-countdown / 3c692554074b27805419a9b0767133a1c8d78150; all dirty WIP preserved. No stage/reset/clean/stash/checkout/commit/push.
