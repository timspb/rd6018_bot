# D146 — exact source-paired node104 release profile for D138

Prepared and validated on 2026-10-31. **Preparation only; no production deployment.**

The complete D124 schema-2 profile is stored at `docs/operations/evidence/D146_D138_NODE104_PROFILE.json`.

- Tracked profile SHA-256: `a2610e4c26c6d2ff6fcd9ac3bc12a1e92aaf0f9d1c49059dcfe5bc2462934e47`.
- Historical prepared-copy SHA-256: `cabf0a0dfd8f92e50dd72926bedf5836394e9f61f14f6a00611ea5a3e977b8eb`.
- The historical copy remains at `/mnt/e/CODEX/RD6018_V3_SAFE_ACCEPTANCE_LUNA_EVIDENCE/D146_D138_NODE104_PROFILE.json`. Its parsed JSON equals the tracked profile; the byte digests differ because the JSON serialization differs. The entrypoint pins the tracked bytes, not the historical copy.
- Old historical deploy marker: `58321a866dd68195bf8264d1d9ebe7c18a60748f`. This is not represented as the exact installed composite Git commit.
- Candidate D138 exact source: `d351c208cbf8666f881a4660df6a0b211170e857`.
- Installed composite D137 app inventory SHA-256 in the canonical D090 inventory format: `9651e979e6394fd53ee373010f845ba00e7ccbbfa85a7a313b95893a0edea444`. **Not** the D137 custom tree digest `691e3ffd...` or the composite preimage digest `f8fa701e...`.
- D138 archive SHA-256: `14277cfeb4738133c32ca1a62be209804f1a4508ef38ad2e3016ed3c726dde63`; source manifest SHA-256: `5cbd7156395183d13ba1f91e0e5bd5bd393308256159d12b10a9d10b1597f469`.
- Node104 original service .env and systemd unit SHA-256 measured and matched canonical old pins; no secrets copied.
- Physical collector pinned SHA-256: `1127e9e3ba52a43ca97ddd8501ea4ac9a52887e708d725fd1299fd22d15a2398`.
- Firmware unchanged: ESPHome `2.3-ha-canonical`, 900-second physical safety lease.
- Git comparison historical marker to candidate has **238 changed paths**, classified as `python_control_change`, without firmware-path changes.
- D124 loader `load_software_release_profile()`: **PASS** both on HOME-PC and again on node104. The same profile SHA was observed on both hosts.

This profile is not an admission of D090's old STARTED transaction, a hardware certificate, or an instruction to switch versions. The D138 candidate is intentionally older than later D139–D146 deployment-tool commits; it is an exact application candidate, not a claim to deploy current GitHub HEAD.

**Next boundary:** use the source-paired D145 entrypoint and D149 observer routing only after a fresh direct ESP Native read and required production admission. The entrypoint now checks the frozen D148 observer before `execute` or `recover`; actual stopped-service recovery and state-preserving restoration on systemd still require operational acceptance without operating the RD6018 output. Keep the current service running until readiness is established.