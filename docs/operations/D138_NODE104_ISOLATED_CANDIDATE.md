# D138 — isolated node104 source + CPython 3.11 candidate

Observed on 2026-10-31, **prepared but never activated**.

- Candidate Git commit `d351c208cbf8666f881a4660df6a0b211170e857`.
- Source archive SHA-256 `14277cfeb4738133c32ca1a62be209804f1a4508ef38ad2e3016ed3c726dde63`.
- 1209 source files; manifest SHA-256 `5cbd7156395183d13ba1f91e0e5bd5bd393308256159d12b10a9d10b1597f469`.
- Offline CPython 3.11 wheelhouse: 45 packages, SHA-256 for each wheel verified using a `D138_WHEELHOUSE_V1` manifest (manifest SHA-256 `4118d452d69082ae7ecc4265bfd26edcf1bd84fc417f5f5a46eb953b55732b44`).
- Isolated candidate venv: 10140 entries, 9325 regular files and 4 symlinks. Tree SHA-256 `d9d344f21b943f19af4becb6e6a63f2cebbf0e298fca26a8dbf4f26cdb66755b`.
- `pip check`: No broken requirements.
- D137 observed installed preimage SHA-256 matches `f8fa701e7362490fcdf61c5e2ab84664c950f3599f56c7eb2477434b603f874c`.
- D138 combined candidate identity SHA-256 `45b6ae0e2dc2f42ee76eaca8311178fd76f92e0254b63e60f3d7393ceee1979e`.
- Final preflight result: `SOURCE_AND_VENV_PREPARED_NOT_ACTIVATED`; `admitted_for_activation=false`.
- Four D138 offline negative tests: 4/4 PASS.

Staging path: `/tmp/d138_stage_d351c208`. This is ephemeral; no claim of production durability. Production `rd6018-bot.service`, `app/`, `venv/`, `state/`, historical `D090_TRANSACTION.json`, deploy-marker, device Output, setpoints, OVP/OCP and 900-second lease were not changed.

Disk-space issue handled by independently offloading historical D103 and D112 temporary test candidates to HOME-PC tar.gz archives with matching SHA-256, then deleting only corresponding transient directories. Disk free increased from 259 MiB to 840 MiB before candidate installation; 402 MiB remained after candidate preparation.

**Release boundary:** This establishes candidate source and environment bytes only. A new independent, crash-safe, state-preserving deployment transaction is still required. Do not call D090 historical `recover`, rewrite the old marker, stop the bot, activate source, or claim production acceptance based solely on this preflight. Fresh device protection and electrical OFF evidence must be checked immediately before any future activation.
