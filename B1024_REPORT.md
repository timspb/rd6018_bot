# B1024 — Native ON/OFF evidence instrumentation readiness

Run: `rd6018-b1024-20261126-r73-native-proof-readiness`
Branch: `codex/rd6018-b1024-native-proof-readiness-20261126`
Base/code HEAD: `a5364c8cdc2e062a91aaef9861b1dd39e137fd91`
Disposition: **SOURCE READINESS ACCEPTED; P3 LIVE EVIDENCE BLOCKED / NOT RUN**

## Scope and outcome

Audited the B1020 Gate 3 evidence requirement against the D091/D106/D149
read-only paths, the live Native transport metadata, the typed Output receipt,
and the application OFF receipt predicate. Confirmed a real evidence assembly
gap: D091 is explicitly OFF-only; D106 collects new direct Native callback
values but projects them only into an OFF proof, omitting connection generation
from its normalized records; no existing reusable tool assembles causal ON and
OFF callback sets against their typed command receipts.

Added one pure offline validator at
`tools/b1024_native_phase_evidence.py` with deterministic fake-only fixtures in
`tests/test_b1024_native_phase_evidence.py`. It consumes captured source
records and typed receipts; it performs no connection, polling, actuator,
lease, persistence, or production integration. It does not generate physical
evidence or claim P3 acceptance. The B1020 Gate 3 live procedure remains
required, and its application-level ON receipt availability is still an open
live instrumentation limitation (below).

## Exact field map and source references

| Evidence | Existing owner/shape | B1024 validator requirement |
|---|---|---|
| Command receipt | `runtime/output/command_receipt.py:13-23` defines `OutputCommandReceipt`: `request_id`, `requested_target`, `terminal_status`, `observed_r18`, `terminal_completed_monotonic`, `connection_generation`, `raw_terminal_identity`. `runtime/physical/transports/esp128.py:557-607` creates it only after terminal `APPLIED` and target/R18 agreement. | Exact typed receipt, nonempty request ID, requested target, `APPLIED`, matching integer R18, finite terminal monotonic time, and integer connection generation. |
| Connection generation | `runtime/physical/transports/esp128.py:50-80` advances generation across connect/close; `:258-298` Native subscribed state metadata carries `source`, `object_id`, `connection_generation`, `status`, `native_type`, `age_s`, callback monotonic timestamp, `key`, and `device_id`. | Every phase's R18, measured voltage and current records must be `esp_native_api` `SensorState`, status `ok`, have integer device and matching receipt generation. ON and OFF phases share device ID and generation. |
| Native R18 and measured V/I | `tools/node104_d106_live_observer.py:121-159` captures typed measurement callbacks, checks the SensorInfo inventory identity, and emits value, native type, device ID and timestamp. | Each callback is strictly newer than its own receipt, fresh within the existing 8-second limit, not in the future; R18 equals the expected state. OFF voltage/current must equal zero. |
| Existing OFF application predicate | `application/start_transaction_validation.py:11-53` validates the typed OFF receipt and a post-receipt Native OFF report in the same generation. `application/start_transaction_service.py` uses that for startup containment. | Existing predicate is retained unchanged. B1024 extends no production behavior; it is an offline paired-phase assembler. |
| D091 | `tools/node104_d091_physical_proof_collector.py:360-425` subscribes for fresh typed measured callbacks; its collector returns a physical OFF proof. B1020 explicitly classifies it as OFF-only. | Cannot by itself provide energized ON proof or a paired causal record. |
| D106 | `tools/node104_d106_readonly_projection.py:22-33,72-120` requires fresh direct Native plus HA records, then explicitly rejects any non-OFF R18/V/I. `tools/node104_d106_live_observer.py:221-275` collects callback records but calls `project_off` and returns only the resulting OFF proof plus provenance. Its normalized record omits connection generation and callback age. | Useful direct read-only source but not an ON/OFF phase logger or assembler. No modification made to D106. |
| B1020 required live sequence | `docs/acceptance/B1020_P3_P8_PHYSICAL_ACCEPTANCE.md:198-228`. | Fresh preflight; single production START; same-ESP post-completion ON R18 and measured V/I; production STOP; post-completion OFF R18 and zero V/I within existing 8-second bound; compare HA only as corroboration. |

### Material limitation found in application exposure

`ExecutionPort.request_verified_on()` at `application/execution_port.py:517-524`
returns `bool(await self._execution_owner.turn_on())`; the application route
does not return the `OutputCommandReceipt` object. The typed receipt exists at
the transport boundary, while the ordinary application ON call erases it to a
boolean. The existing OFF verified-clearance path does expose a typed receipt
(`ExecutionPort.request_emergency_off_receipt`, around line 419) and validates
the following Native report. Therefore the offline assembler is useful only
when an authorized operator's existing route provides the typed receipt or an
existing captured transaction artifact can be linked to it. It does not add a
second physical observer or alter the production route. If the supervised
candidate cannot retain the ON receipt and Native callback fields, B1020 Gate
3 remains **BLOCKED**; do not derive a receipt from an ACK or issue alternate
commands.

## Verification

- Focused project-venv command:
  `PYTHONPATH=.:tests:tools TG_TOKEN=<inert-local-value> /home/home-pc/.venvs/pcp-test/bin/python -m unittest -v tests.test_b1024_native_phase_evidence`
- Result: **5/5 PASS**, exit 0. Cases cover valid ON/OFF pair; cached-HA-only,
  stale, pre-command and wrong Native type; device/generation/R18/receipt
  mismatches; nonzero post-OFF voltage/current; ambiguous receipt; reordered
  phases.
- `git diff --check`: PASS.
- No broad test suite or repeated CI run.

## Decision and boundaries

- Offline implementation: **PASS** (validator behavior only).
- P3 Gate 3 actual Native ON/OFF evidence: **BLOCKED / NOT RUN** pending a
  separately supervised session and availability of the production ON receipt
  plus the phase callback records. No fixture result is physical evidence.
- P3 overall and P8: **HOLD**; no checklist item closed.
- Requested context says Draft PR #182 accepted and prior GitHub CI #2244 and
  ESPHome dummy build #163 succeeded; neither was queried here or treated as
  evidence for this uncommitted HEAD.
- No node104, ESP/HA, RD6018, Output, setpoint, firmware, service, production,
  SSH, network/GitHub, original dirty worktree, staging, commit, or push action.
- No shared checkpoint/master/handoff/runbook edits. Controller reconciliation
  remains outstanding.

## Next supervised step

During a separately authorized, attended B1020 run, preserve the actual typed
ON receipt if the accepted production route exposes it, then capture raw
`get_native_physical_output_report`/measured Native callback envelopes without
substituting HA. Include per-record `source`, `native_type`, `status`, `device_id`,
`connection_generation`, `subscription_timestamp_monotonic`, and `age_s`; use
the receipt's target, terminal status, observed R18, completion time and
generation. Apply the offline validator to both phases. If the ON receipt or
same-generation callback cannot be retained through the existing authorized
route, record **BLOCKED** and leave the hardware untouched.


## Independent controller acceptance — B1024
Controller inspected the real pure validator, its five fixture cases, the unchanged `OutputCommandReceipt` schema and the application `ExecutionPort.request_verified_on` bool return. HOME-PC project venv independently reran B1024 along with ESPHome intrinsic safety, safety lease, runtime safety and edge lease: **49/49 PASS**, exit 0. No direct Native hardware collection or actual typed ON receipt was obtained. The application's bool-only ON route is a genuine unresolved production evidence *exposure* gap, not proof that ON commands are unsafe or that the P3 hardware gate has passed. The next B1026 source-only task will examine a minimal supported, non-actuating receipt observation seam while retaining the existing bool API and sole ExecutionPort authority. Current B1024 offline validator remains a consuming/validation tool only; it does not invent receipts or access hardware. P3/P8 unchanged HOLD.
