# Integrations — ownership contract

**Status: operating boundary documented; department functional-owner approval OPEN.** Primary ADRs remain the decision authority. This file records accepted decisions and conservative inventory classifications; placement under this department does not assign ownership.


### B902 current P1 scope reconciliation (2026-11-25)
AD083 D061 function scopes are accepted with the boundaries recorded in `docs/RD6018_AD083_CONTROL_ADOPTION_OWNER_DECISIONS_2026-11-15.md`. The file has no whole-file owner. D062 MIX authority remains separate in `rd_managed_mix.py`. The current 517-row source registry and historical 82-path subset were reconciled from B900 evidence; no registry-wide reanalysis was repeated.

## Responsibility and boundaries

- Planned responsibility: Integrations as defined in `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` (department table, lines 12–24).
- The production functional owner, cross-department state/decision owner map, and final whole-file owner assignments remain OPEN unless an exact primary ADR below approves the bounded responsibility.
- Interfaces are the existing function/module APIs cited per path; this contract authorizes no file moves, API changes, new state, side effect, or compatibility shim.
- Consumers, callsites, side effects, and dependencies are summarized from the AD148AN source/call graph review. Verify against current source before implementation; this checkout has extensive dirty WIP.

## State, decisions, and interfaces

- State and decisions remain with their specifically cited existing owners. Only a row still classified CANDIDATE / NOT APPROVED is unapproved; APPROVED path rows are limited to the cited primary ADR scope. Cross-department orchestration stays with existing callers and ports.
- Inputs/outputs follow current callable signatures and DTOs; no inferred API expansion is approved. No UI/Application direct hardware access; physical effects remain behind existing execution boundary.

## Consumers, effects, dependencies, tests, migration

- Exact source paths and caller/test evidence are listed in the inventory below. These paths are evidence pointers, not authorization to change them.
- Migration constraint: preserve current public imports, persisted formats, operation order, safety/verified-OFF semantics, and caller behavior. Any future extraction needs a separate bounded ADR and focused parity tests.
- Risk: matrix source observations came from a dirty checkout; candidate recommendations are not approvals, and some rows lack production reachability evidence.

## 2026-11-25 — B900 current functional scope reconciliation

The B900 review records accepted function/module scopes against current production callers and the cited primary decisions. These entries do not imply blanket department sign-off or whole-file approval. The current 517-row source registry and historical 82-path approval subset were reconciled from existing B893/B899 ledgers; categories were mapped without replaying or double-counting prior rows. B902 accepts the bounded D061 function scopes in `rd_managed_adoption.py` after false/exception/cancellation verification; its whole-file owner remains intentionally blank, and D062 MIX authority remains in `rd_managed_mix.py`.

## Path assignment register

| Classification | Path | Primary ADR / scope | Caller evidence / tests |
|---|---|---|---|
| REGISTER NOTE | — | Individual path decisions appear below; department functional-owner sign-off remains OPEN. |
| MIXED-SCOPE | `hass_api.py` | AD057, master plan line 1014 — Integration boundary is not permission to bypass ExecutionPort/Safety. | Hass client/facade combines integration adaptation with live data and command-facing methods. Tests: No path-specific test identified in this bounded matrix; focused test evidence remains OPEN. |

## Unassigned decision rules

- **APPROVED:** individually APPROVED rows are approved only within the cited primary ADR scope.
- **CANDIDATE / NOT APPROVED:** only rows still marked CANDIDATE / NOT APPROVED remain unresolved.
- **BOUNDED AD014:** preserve the five exact function/state boundaries and keep whole-file final owner blank.
- **MIXED-SCOPE / ADAPTER/COORDINATOR / INSUFFICIENT-EVIDENCE:** remain unassigned.
- **HOLD:** `rd_managed_adoption.py` remains under AD083 HOLD and is not part of the 81-row matrix.

## Sources

- `docs/RD6018_MODULARIZATION_EXECUTION_PLAN_P0-P9_2026-11-17.md` — canonical department names, P1 checklist and status.
- `.recipe-studio-local/REPORT_MOD_P1_AD148AN_FINAL_OWNER_MATRIX_20261117.md` — 81-path evidence/classification matrix; recommendations only.
- `.recipe-studio-local/REPORT_RD6018_P1_FINAL_OWNER_PERSISTENCE_RESOLUTION_20261118.md` — 37/5/39 reconciliation and approved persistence model.
- Exact primary ADR references are recorded per path above; ADR text, not this summary, governs scope.

## 2026-11-18 — P2/P6 connector evidence boundary

- `hass_api.py` remains MIXED-SCOPE and has no whole-file owner approval. Production composition selects `PhysicalConnectorFactory`; `ESPDirectConnector` delegates callback-backed reads to `ESPHomeTransport`, while `HAESPConnector` delegates its read model to `HA102Transport` and retains the HA REST sidecar only as a separate read path. No second Native observer or normalized-evidence pipeline was found.
- Native Guard pre-ON evidence is selected only by `HassClient.get_native_guard_pre_on_snapshot()` from an `ESPDirectConnector` and requires callback source/type/monotonic freshness. HA timestamps and fetch time in `HA102Transport` are separate. Native terminal command receipt, subsequent physical R18 readback, and HA diagnostics remain distinct; no OFF inference from current=0.
- This audit found no supported connector contract defect and authorizes no split or API change. See `.recipe-studio-local/REPORT_RD6018_P2P6P8_EVIDENCE_BATCH_20261118_02.md`. The integration department owner stays OPEN.


## 2026-11-18 — P6 Telegram battery-selection layout and deferred BW600 seam

- P6 production seam: `production_bot_ui.py` retains battery page state, durable callback lookup, registry access and installed action handlers. Pure callback token/data encoding and keyboard row layout now belong to `runtime/ui/telegram/battery_selection.py`. Three prior imports remain direct compatibility aliases; callback prefix `v2_battery_id_`, 12-character deterministic token and row order unchanged. No added authorization or physical-control owner.
- Independent Windows project venv regression: seven modules, **43 PASS + 4 subtests PASS**, including explicit export-identity and existing-message callback encoding checks. Physical hardware, node104, firmware, source selection, setpoints and charging policy untouched. P6 *battery selection presentation subgate* accepted; the whole P6 remains OPEN.
- Deferred future BW600 connection, under existing P0–P9 (NOT implemented now): **RD6018** alone owns charge recipes, stage decisions, and its existing ExecutionPort; **BW600** will be a separate electronic load/discharge and measurement integration; **XH-CDC-MK** owns switching the charger branch, independent of charge regulation. No second charging engine or concurrent autonomous BW600 CDC FSM. Do not repurpose RD charge TelemetrySnapshot fields for BW600 observations.
- Future P2: review independent BW600 command/readback and measurement contracts within existing port/evidence architecture. Future P3: reciprocal fail-closed admission: prove fresh real BW600 load-OFF before RD charge enable; prove RD Output OFF and no charge current before BW load enable. USB command ACK, current-derived Load OFF and relay intent are NOT sufficient physical readbacks. Future P6: separate load telemetry provenance/freshness and XH switch evidence, only after actual revision/protocol evidence. No adapters, DTOs, interlock, HID transport or switch commands are authorized/created in this slice.
- Critical pending hardware facts: ordered XH-CDC-MK revision, effective Con+/Con− charge connection with RD Output OFF, genuine switch readback, BW600 remote CDC/relay command decoding, ETS while load OFF and power-loss behavior. Existing research: `docs/assistant/BW600_XH_CDC_MK_RESEARCH_2026-11-09.md`; boundary audit: `.recipe-studio-local/REPORT_RD6018_BW600_BOUNDARY_AUDIT_20261118.md`. Preserve original P9/DoD rule: start implementation of BW600 **after** RD6018 full modularity and release acceptance.

## 2026-11-18 — P2 integration provenance review (batch 03)

- Production observation remains split by existing integration source: Native callback metadata does not become HA freshness, command receipt, or verified physical post-command readback. No source normalization pipeline or new owner was added.
- Current system Linux 3.12 lacks `aiogram`, `aiohttp`, and `aioesphomeapi`; corresponding integration imports are reported as errors, not passes. Detailed results: `.recipe-studio-local/REPORT_RD6018_P8_P2_INTEGRATION_BATCH_20261118_03.md`.
# 2026-11-19 — P7 runtime/composition batch 10 review

- Cross-checked `runtime/production_runtime.py` handler, worker and lifecycle responsibilities against `.recipe-studio-local/REPORT_RD6018_P7_RUNTIME_FACADE_CROSSWALK_20261118.md`. Existing composition and functional owners remain authoritative; no new transport, normalization or runtime owner was supported. `hass_api.py` sidecar close correction is already implemented and recorded under physical-execution ownership.
- No production source/API change and no whole-file owner assignment. Registered unmanaged Output OFF callback regression candidate and Linux dependency block are recorded in `.recipe-studio-local/REPORT_RD6018_P7_RUNTIME_DECOMPOSITION_BATCH10_20261119.md`. P7 remains OPEN; P8 remains HOLD.


## 2026-11-19 — P7 batch-10 independent acceptance

- HOME-PC Luna run `rd6018-mod-p7-runtime-facade-decomposition-luna-20261119-10` exit=0; R7.2 event `2ea10d8a314246f9820ad97ab898e602` ACK first attempt. Independent native Windows project venv five-module cohort **58 PASS**, exit=0.
- Two fake-only tests exercise actual registered unmanaged Output OFF handler: verified OFF precedes lease disarm and success acknowledgement; verified-OFF failure returns alert without disarming or reporting success. No production source/physical changes. Bounded P7 callback software subgate ACCEPTED; P7 overall OPEN, AD080 whole-file owner HOLD, P8 and physical acceptance HOLD.


## 2026-11-19 — P7 HA REST read/freshness boundary, batch 23

`HassClient` remains the compatibility owner for the independent HA REST sidecar and its legacy entity map, session seam, bulk-to-concurrent-GET fallback, source timestamp metadata (`_ha_last_reported`, `_ha_last_updated`, `_ha_last_changed`, `age_s`) and status diagnostics. `HA102Transport` remains a distinct typed-config transport owner; its config/entity map/session and output shape do not match this legacy facade contract. The selected backend bypass in `HassClient.get_all_live()` and `canonicalize_live()` call are preserved. `runtime.telemetry.source.normalize_live()` remains dormant without a production caller. No existing compatible owner/API was identified for this entire bounded cluster, so batch 23 makes no source move and approves no new owner. Native output/Guard evidence remains ESP Native-only, independent from HA timestamps. See `.recipe-studio-local/REPORT_RD6018_P7_HASS_API_READ_BATCH23_20261119.md`; test collection limitations and remaining acceptance are recorded there. P7 remains open, P8 physical/release remains HOLD, AD148 final-owner remains HOLD.


## 2026-11-19 — independent HA sidecar batch-23 review and Windows evidence

- HOME-PC Codex Luna batch 23 completed exit 0 and emitted an R7.2 event. Source inspection confirmed ownership-blocked HA REST reader extraction; production code/tests unchanged. No merge of native read authority with HA REST sidecar.
- Independent Windows project .venv: 48 PASS + 5 subtests, 1 FAIL during import, due to node104_d106_readonly_projection importing Unix-only fcntl transitively from node104_d090_transaction. This is a D106 portability boundary, not evidence of ESP transport failure. No full Windows PASS claimed; D090 release/actuator contract untouched.
- P7 HA transport split remains BLOCKED by existing owner contracts, P7 PARTIAL; P8 full/physical release HOLD; AD148 whole-file HOLD; node104 HANDS_OFF. No live device or deployment actions.

## B896 accepted optional AI responsibility (2026-11-25)

`integrations/ai/` owns the optional AI implementation: prompt data, AI-only context/history/trend and strategy snapshot formatting, external AI request/response handling, and AI analysis presentation/dialog logic. It is read-only advisory and has no charge-transition, persisted-session, Output/V/I/protection, lease, or background-task authority. `ai_engine.py`, `ai_system_prompt.py`, and former AI presentation modules are compatibility/dispatch boundaries only. Application owns shared operator read projections and their typed source; Telemetry owns evidence provenance; UI/Telegram owns screen, callback registration, and transport contracts; production composition/lifecycle retains lazy wiring and task ownership.

Evidence: B896 reconciled the nine `integrations/ai/*.py` modules and their compatibility edges in `reports/B893_FINAL_OWNER_REGISTRY.csv`, `reports/B893_EFFECT_REVIEW.csv`, and `reports/B896_B892_SOURCE_DELTA_OWNER_RECONCILIATION.csv`. This is a scoped responsibility record, not department-wide approval of unrelated Integration paths.

## B910 AI compatibility contract review (2026-11-25)

The top-level `ai_engine.py` and `ai_system_prompt.py` remain compatibility exports. The former has current direct test consumers and its exported callable identity is asserted; the latter has no direct in-repository import found, but this owner contract still names it as a supported compatibility boundary. `runtime.production_runtime.__getattr__` also exposes the same AI callables and prompt lazily, and the dialog path resolves those names at callback time. B910 adds a focused identity regression for the prompt facade and runtime lazy exports. This evidence does not authorize removal: deprecation requires an explicit public-consumer/support decision covering callers outside this repository and preserving runtime callback injection. No AI behavior or authority changed.
