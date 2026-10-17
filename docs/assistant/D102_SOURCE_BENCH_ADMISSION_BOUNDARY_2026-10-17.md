# D102 — exact-source bench admission audit
Date: 2026-10-17.

## Implemented boundary
Source-only, read-only tool: `tools/node104_d102_bench_admission.py`.

It verifies the exact accepted D101 source identity for b44476b:
- Commit: `b44476bcd19dbf0f4ac955634f02a4a7f9e51ddc`.
- source.tar SHA-256 `89bb7a891c590fcd72eeb14fedd6e8405690528b627ff9ce56b91a7a91781294`.
- RELEASE_MANIFEST.json SHA-256 `bebb447abf423ab3295866d95990fd2b575164dd716555f69201f9403d7e5c76`.
- 1022 accepted source files: archive paths, member types, bytes, no duplicates, and extracted tree.
- Explicit no-symlink/no-extra-files protection.

This gate reads the already-created offline review stage and produces a structured
readiness report. It does not contact node104, open native HA/ESPHome devices, install
software, manage a service, sign anything or execute physical actions.

The source verifier is intentionally **not** an alternative D090 owner. Its result
`SOURCE_ONLY_PASS_PHYSICAL_ADMISSION_OPEN` always carries
`production_activation_authorized=false` and
`physical_trial_authorized_by_this_report=false`.

## Actual D102 result

HOME-PC input:
`E:\CODEX\RD6018_D101_REVIEW_STAGE_b44476bcd19d`

Machine-readable output:
`E:\CODEX\RD6018_D102_BENCH_ADMISSION_20261017.json`

- Source identity, all member hashes and extracted tree **PASS**.
- All **13** mandatory groups from the canonical D090 source remain
  `OPEN_EXACT_SOURCE_FIRMWARE_EVIDENCE_MISSING` for this Python/firmware pairing.
- Review of the **exact installed** ESPHome binary digest is unresolved.
  Neither the checked WSL source checkout nor searched node104
  project/home artifacts exposed a firmware.bin; the native ESPHome project
  version `2.2-autonomous-authority` is not an installed-flash SHA-256 proof.
- Accepted physical-record signature trust root is still unset in D090.
- Installed production is still the old exact source
  `8b75cca153f00847d84396aba392472bb7552ad4`.
- D097 candidate-only `autonomous_status` has been proven read-only,
  but production-mediated Enter/Exit under the new source remains open.

## Required next reviewed engineering gate

Resolve how the installed ESPHome 2.2 firmware can be tied to a verified binary
image (artifact or independent authorized flash readout); distinguish a freshly
compiled but never flashed image from the actual installed one.
Carry forward genuinely applicable D095/D096 real edge evidence but do **not**
reclassify it as D097 exact new-source production acceptance.
A separately reviewed physical bench transition, with the existing atomic
rollback chain and genuine live evidence, is required before final D090.
The original D090 source, firmware and signing pins must not be silently
rewritten or weakened to unlock this stage.

## Validation

Local negative tests in `tests/test_node104_d102_bench_admission.py`:
valid source-only report, altered extracted file, added file, corrupted archive,
mismatched commit and symlinked extracted tree (6/6 PASS).
