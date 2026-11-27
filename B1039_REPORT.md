# B1039 — finite source-paired P3/release preflight

**Run:** `rd6018-b1039-20261127-r73-source-paired-p3-readiness`
**Exact source HEAD:** `0ab16b187ef1c1d41a9de41d4d6450f8277ddc98`
**Branch:** `codex/rd6018-b1039-source-paired-p3-readiness`
**Scope:** offline source artifacts and operator evidence hookup. No source code changes, node104/ESP/HA/network/GitHub access, service, firmware, lease, setpoint, Output, deployment, commit, or push.

## Result

**SOURCE STAGE: PASS. D124 candidate admission: BLOCKED. P3 physical acceptance: HOLD. P8 physical/release: HOLD.** The existing `node104_atomic_deploy.py stage` command completed against the exact frozen commit. The output is a generic tracked source archive, not a D138 app+venv candidate or an installable release. A machine-readable B1039 manifest is at `/tmp/rd6018-b1039-source-pair/B1039_CANDIDATE_MANIFEST.json`; its target-specific fields are null, and it is intentionally not a D124 schema-2 profile.

## Exact staged artifact

Directory: `/tmp/rd6018-b1039-source-pair/release-0ab16b187ef1c1d41a9de41d4d6450f8277ddc98-er103eue`

| Artifact/fact | Result |
|---|---|
| Source commit | `0ab16b187ef1c1d41a9de41d4d6450f8277ddc98` |
| Manifest schema / tracked files | 3 / 1,804 |
| `source.tar` size | 23,941,120 bytes |
| `source.tar` SHA-256 | `1f22c0ec2142991d442fd02f454bcc49623454d77ef4af2d818a9a7db7b4d93b` |
| `RELEASE_MANIFEST.json` SHA-256 | `fb5b58bb3e350bafe327e3d4e7fd296f66b7dc27dfaefd878c3e40734893a097` |
| `STAGED_OK` SHA-256 | `e13524903093872c951016fbc6b48a469da08bfec05593234b03b0be399d9168` |
| Manifest marker binding | manifest hash matches; schema 2; `tree_verified=true`, `directory_fsync=true` |
| Independent archive check | fresh `git archive` bytes and SHA matched staged `source.tar` exactly |
| Extracted tree | existing `verify_manifest()` passed against all 1,804 declared files |
| B1039 candidate manifest SHA-256 | `51e41b9a6432f1c07ccd55eb04b4dbc12b799c29a59146437c4febf536944cf1` |

The stage archive and manifest are out-of-tree, so no profile embeds a self-referential archive identity in Git.

## Source facts vs target observations

| Field | Classification | Evidence/status |
|---|---|---|
| Candidate source SHA | Independently verified | Exact HEAD and stage manifest agree |
| Candidate source archive SHA | Independently verified | Manifest value, staged bytes, and independent `git archive` bytes agree |
| Staging manifest/marker and extracted tree | Independently verified | Existing stager and `verify_manifest()` pass; marker binds manifest SHA |
| D124 schema-2 shape and rules | Independently verified | `load_software_release_profile()` loads tracked historical D146 profile; B1039 manifest is rejected (`ValueError: invalid release profile schema`) |
| Historical D145 source/preimage/profile pins | Independently verified from tracked source | Source `d351c208cbf8666f881a4660df6a0b211170e857`; preimage `9651e979e6394fd53ee373010f845ba00e7ccbbfa85a7a313b95893a0edea444`; profile SHA `a2610e4c26c6d2ff6fcd9ac3bc12a1e92aaf0f9d1c49059dcfe5bc2462934e47` |
| D147/D150/D151 expected constants | Independently verified as tracked constants | D147 `1127e9e3ba52a43ca97ddd8501ea4ac9a52887e708d725fd1299fd22d15a2398`; D150 `d9d4190c61eda4ecf690d150572be8847b4cfb60860c901d4acfaf517845bdef`; D151 `9500454a068d120f0b23740ad3933eb70ebd8cf24fbaa7c03ddafd3e729cb8d9` |
| D151 collector bytes in this checkout | Not available | D149’s referenced node-relative D151 path is not tracked here; the current router tests use synthetic fixture bytes. The immutable D151 expected hash was not changed or represented as a local byte verification. |
| Current node104 old source and composite app/venv/state preimage | Unverified/null | Requires an authorized current read-only observation; historical D146 is not a substitute |
| Current service/Python/unit/`.env` metadata and firmware identity | Unverified/null | No node or Native API access in this source-only task |
| Current direct Native state: R18, U/I, battery, Vset/Iset, R16, lease, trip/quarantine/autonomous | Unverified/null | No live collection; no physical claim |
| Installed D147/D151 paths and identities | Unverified/null | Tracked expected constants do not prove node installation |
| Exact old-to-candidate `changed_paths` | Unverified/null | Old installed source is unavailable |
| D138 app+venv candidate for this HEAD | Not produced | Generic source stage contains no venv; it is not a D138 candidate |

## D124/D145/D149 disposition

The D124 loader requires a complete schema-2 profile, including distinct old/new source identities, target identity, firmware/Python contract, service and environment metadata, source archive/manifest, preimage inventory, unique `changed_paths`, and proof collector identity. Only candidate-side source SHA/archive/manifest are established here. The out-of-tree manifest preserves these exact fields and uses explicit `null` for absent target evidence; it cannot be loaded as a D124 profile.

The current tracked D145 entrypoint remains pinned to historical D146 source `d351c208cbf8666f881a4660df6a0b211170e857`, historical preimage `9651e979e6394fd53ee373010f845ba00e7ccbbfa85a7a313b95893a0edea444`, and the historical profile bytes. These pins were inspected and left unchanged. D145 profile admission compares the historical profile’s `proof_collector_sha256` to `D147_SHA`, while the separately selected state-preserving execution/recovery path verifies and routes to `D151_SHA`. This is a **phase-specific distinction** in the existing source, **not by itself evidence of an ABI conflict**. D151’s immutable expected hash remains `9500454a…cb8d9`; its exact collector bytes and current node installation are not verifiable from this checkout. Do not repin or substitute D145/D151. A new source release still requires a coherent reviewed source/tool/profile pairing after the missing observations and candidate artifacts exist.

## Same-app P3 callback hookup

The hookup uses the existing `ExecutionPort` and helper only. It creates no observer, client, timer, authorization gate, or actuator route. The snippet records the exact existing typed receipt and phase result; it does not itself initiate an operation. Place the callbacks on the already-approved operator-supervised ON and canonical emergency-OFF calls only when a separate physical procedure is authorized:

```python
import time
from tools.b1038_app_on_off_pair import pair_execution_port_callbacks

on_callback_values = []
off_callback_values = []

def capture_on(receipt, phase_result):
    on_callback_values.append((receipt, phase_result))

def capture_off(receipt, phase_result):
    off_callback_values.append((receipt, phase_result))

# On the existing, separately authorized operation only:
# await execution_port.enable(
#     existing_intent,
#     identity=existing_identity,
#     recipe_voltage_ceiling_v=existing_recipe_voltage_ceiling_v,
#     on_native_phase_observed=capture_on,
# )
# On that procedure's canonical emergency-OFF operation:
# await execution_port.request_emergency_off_receipt(
#     on_native_off_observed=capture_off,
# )

pair = pair_execution_port_callbacks(
    on_callback=on_callback_values[-1],
    off_callback=off_callback_values[-1],
    now_monotonic=time.monotonic(),
)
```

Only existing observed values are passed: each tuple is `(OutputCommandReceipt, phase_result)`. Preserve the callback fields `source_transport`, `source_client`; `records.output_r18`, `records.voltage_v`, `records.current_a`; and each record’s `sensor_info`, `state`, `native_type`, `source`, `status`, `object_id`, `key`, `device_id`, `connection_generation`, `subscription_timestamp_monotonic`, and `age_s`. The helper checks exact object identity across requests, receipt target/status, Native `SensorInfo`/`SensorState` provenance and consistency, one device, terminal/callback ordering, no more than the existing 8-second age, and zero measured U/I after OFF. Its result is `SOURCE_PAIR_CONSISTENT` / `physical_p3_status=NOT_ESTABLISHED_SOURCE_ONLY`.

This pair must be accompanied by independent fresh direct ESP Native evidence, including target identity, live R18 and measured U/I, raw R16 and existing 900-second lease state (armed/generation/remaining/Modbus age), trip/quarantine/autonomous and temperature. R16=1/2 are observable/operator-managed only; R16=3 and unknown nonzero remain fail-closed. Neither callback helper output nor old reports/HA cache authorize ON/OFF or establish physical PASS. The live action and collection require separate owner supervision; neither is authorized here.

## Five remaining canonical P3/P8 checkboxes

These are the three unchecked P3 and two unchecked P8 physical/release items in the canonical 103-check list. P0–P9 remains 98/103.

1. **P3 — Confirm V/I programming/readback, ON/OFF, Native receipt, and causal evidence.** Under separate owner authorization, use the existing running application and sole ExecutionPort; capture the exact ON callback and canonical emergency-OFF callback above; retain typed receipts and same-app Native phase fields. Independently capture fresh ESP Native identity, R18, measured U/I and relevant timestamps. Require the helper’s internally consistent result and independently review the causal sequence. Missing/stale/mismatched evidence or nonzero post-OFF U/I keeps this unchecked.
2. **P3 — Separately pass the allowed hardware gate for R18/OPP/lease.** In the owner-supervised bench evidence, verify direct Native R18, raw R16 behavior, and existing ESP-local 900-second lease semantics including state/generation/remaining/Modbus age; include independent actual V/I and temperature. Verify R16=3 and unknown nonzero fail closed; R16=1/2 remain observational/operator-managed. Do not change thresholds, lease configuration, or firmware under this task.
3. **P3 — Keep node104 and equipment untouched until separate authorization and release gate.** Record the owner’s separate authorization and accepted release boundary before any physical/deployment work; no node/service/firmware/lease/Output operation is part of this preflight. This remains unchecked now because no such authorization or release acceptance was supplied.
4. **P8 — Separately resolve and document physical acceptance.** Independent acceptance reviews the live direct ESP Native capture, same-app callback pair, target/device identity, R18/U/I, OPP/unknown-R16 behavior, lease and safety evidence. Source/fake evidence alone cannot check this item.
5. **P8 — Consider node104 deployment only after accepted release.** First obtain a real D138 app+venv candidate and complete exact D124/D145/D149 source/tool/profile pairing; verify the intended D147/D151 phase-specific pairing without changing immutable historical D151; complete existing release, rollback and fresh physical prechecks. Deployment remains a later separately authorized operation, never implied by this stage.

## Refresh after a future commit

After the intended source/docs are finalized and committed, use the resulting exact new commit SHA (do not reuse or pin this report’s SHA):

```bash
PYTHONPATH=.:tests:tools TG_TOKEN=inert \
  /home/home-pc/.venvs/pcp-test/bin/python tools/node104_atomic_deploy.py stage \
  --repo "$PWD" --sha <FUTURE_COMMIT_SHA> \
  --staging /tmp/rd6018-b1039-source-pair
```

Then independently hash `source.tar`, `RELEASE_MANIFEST.json`, and `STAGED_OK`; compare a fresh `git archive` byte-for-byte; run the existing `verify_manifest()` against `tree`; regenerate the external candidate manifest. After separately authorized current read-only observations provide the missing target data, build a true D138 app+venv candidate, calculate exact changed paths from the observed installed source, run the actual D124 loader, and independently review one coherent D145/D149/D151 pairing. Do not put the generated profile in the tracked archive or lock a later source revision to this report’s digests.

## Verification performed

Using `/home/home-pc/.venvs/pcp-test/bin/python`, `PYTHONPATH=.:tests:tools`, and inert `TG_TOKEN`:

- Existing `node104_atomic_deploy.py stage` on exact HEAD: PASS.
- Existing staged manifest/tree verifier and independent archive byte/SHA comparison: PASS.
- Existing D124 loader on tracked D146 profile: PASS; candidate manifest rejected as intended; no missing target value was fabricated.
- Focused `tests.test_node104_atomic_deploy` + `tests.test_node104_d145_entrypoint`: **26 PASS**.
- P3 helper was source-reviewed against exact `ExecutionPort` signatures and B1038 fields; no live operation run.
- This report adds docs only. No full suite, hardware, node, ESP/HA, deployment, firmware, service or Git remote operation.


## Independent controller correction — D145/D147 vs D151

The worker originally labeled the D147 profile pin and D151 state-preserving routing as a current ABI conflict. Inspection of the actual D145 entrypoint and D149 router shows this is a mode-specific design, not sufficient evidence of an incompatible interface. The offline candidate manifest was corrected accordingly and its SHA-256 recomputed. No historical pin or target state was changed.
