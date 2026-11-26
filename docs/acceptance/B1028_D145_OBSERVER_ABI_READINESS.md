# B1028 — D145 observer ABI readiness and source-pair handoff

**Source/fake ABI result: PASS. Candidate admission: NOT READY. Physical/release acceptance: HOLD.**

## Verified current software contracts

| Boundary | Current contract | Offline result |
|---|---|---|
| D144 transaction → D145 evidence adapter | Keyword `require_stopped`; execution order PRE_STOP ×2, STOPPED, POST_START ×1 | Existing owner-binding fixture passes |
| D145 adapter → D090 recovery proof | Keyword `require_service_stopped`; source-paired current validator also receives `allow_active_session` and `software_release` | Current tracked signatures align; do not mix with historical installed module |
| D090 owner → D149 router | Zero-argument proof callback | Router fixtures pass |
| D149 phase routing | D147 PRE_STOP / D150 STOPPED and POST_START / D151 RECOVERY; state-preserving D145 execute explicitly selects D151 for every boundary | Route and recovery-environment fixtures pass |
| Recovery state | `D090_STATE_PRESERVING_RECOVERY=1` for D151; state documents/quarantine are preserved | State-preserving fixture passes |
| Stale/invalid proof | Wrong phase flag, unknown phase, bad schema/nonces, altered or unsafe observer fails closed | Wrong-phase fake-owner probe PASS; router negative fixtures pass |
| Owner callback lifecycle | Original `owner.proof` restored in `finally` after execute/recovery success or failure | Existing failure-restoration fixtures pass |

The historical installed `validate_physical_off` signature mismatch is not resolved by a compatibility shim. Use a coherent source-paired release so D090 transaction code and its validator come from the same reviewed candidate. The current tracked source contains the expected `allow_active_session` and `software_release` arguments.

## Exact candidate path

1. **Freeze source first.** Finish and review all tracked changes, then identify the exact clean source HEAD. Do not edit tracked files after this freeze. Generate the source archive/tree and existing stage manifest with the repository’s offline staging owner. Keep archive/manifest outputs outside the tracked source tree.
2. **Assemble the existing D124 schema-2 profile externally.** Start from the B1023 skeleton only as a field checklist, not as a valid profile. Populate candidate source/archive/manifest from the frozen artifact and obtain old installed source plus composite app/venv/state preimage, service/unit/Python metadata, firmware, and observer identity only from the authorized live read-only collection. Keep the completed profile outside the source archive; this avoids a self-referential archive identity. Do not repin the historical D145 entrypoint or claim the B1023 NOT VERIFIED fields as facts.
3. **Perform read-only node proof through the existing approved collector path.** Obtain fresh direct ESP Native callbacks and the existing independent observer evidence required by the D091 proof contract; preserve timestamps, identities, source provenance, R18, measured U/I, lease/trip/quarantine state, and the required service/process observations. This is observation only; no D090 transition or service mutation.
4. **Review source/tool/profile pairing before owner admission.** The currently tracked `tools/node104_d145_entrypoint.py` and default profile are explicitly pinned to historical D146 (`d351c208cbf8666f881a4660df6a0b211170e857`) and cannot admit this candidate. Therefore the frozen candidate must include a separately reviewed D145 tool/profile pairing that consumes the external completed profile through the existing D124 loader and existing D090/D144 owner, while preserving D149 routing and the single owner lock. Do not alter or overwrite historical D146 evidence, and do not create a parallel owner or weaken profile validation. Until that source-paired tool/profile set exists and is independently accepted, the current entrypoint is not a candidate admission route.
5. **Keep acceptance gates separate.** Passing offline profile loading and source-pair checks is not node proof, physical acceptance, or release acceptance. P3/P8 remain HOLD until their existing explicitly authorized evidence is completed. No deployment or physical action follows from this readiness note.

This sequence adds no authorization system, digest-pinned acceptance gate, signature, service, observer, or permission. It uses existing D124 profile, D090 owner, D144 transaction, D149 router, and read-only proof contracts. Historical digests in the existing immutable observer/source code remain ordinary implementation integrity checks, not new authorization claims.

## Scope comparison

Against historical D146 source `d351c208cbf8666f881a4660df6a0b211170e857`, the requested source HEAD differs by 1,008 files (113,355 insertions, 15,797 deletions) across the accumulated modularization branch. D145/D149-specific additions are `tools/d144_owner_binding.py`, `tools/d144_state_preserving_transition.py`, `tools/d149_observer_router.py`, and `tools/node104_d145_entrypoint.py`; D090 release/transaction modules are modified. See `B1028_REPORT.md` for the complete focused file list and test evidence.

## Status

Source HEAD audited: `170aa91a7e7d8bc578f5dfa32d7fea12f411f9fa`. Offline fixtures: 31/31 PASS; separate stale PRE_STOP phase probe PASS. No source defect or source patch. P0–P9 98/103; P3 three gates and P8 two gates HOLD. This document does not claim a current physical read, installed artifact identity, accepted profile, release, or deployment.
