# D133 node104 live byte baseline — 2026-10-31

Captured using `tools/d133_live_byte_baseline.py --pid 162141` on node104, reading installed bytes only; not a deployment promotion or a signed release.

| Field | Captured |
|---|---|
| Installed `app/` file count | 1194 |
| Canonical app tree SHA-256 | `691e3ffd0b612d6832e8cd95030196f42ac384138c68ffd6b1e3545d85afd669` |
| D090 CLI SHA-256 | `5374b89814baa1260f59df63941a35dfcde390dae4ba955a91094bd7c62bd938` |
| Service PID/entrypoint | `162141`, `app/bot.py` matched |
| D090 transaction | `818df047a6e64a22905d6da900162a86` |
| D090 status | `STARTED`, no candidate inventory |
| Historical deploy marker | `58321a866dd68195bf8264d1d9ebe7c18a60748f` |
| Claimed D090 candidate source | `930239c670899e14ccb09154d99baf77df90da10` |
| Session | `RETIRED`, OFF evidence matched, quarantine false |

The tree hash is computed over sorted path, file length, SHA-256 and executable-bit records; `__pycache__`, `.git`, and `.pytest_cache` are excluded. The collector fails on symlinks or special files. It hashes only D090 CLI content and the marker, never prints `.env`, tokens, raw state or firmware credentials.

**Interpretation:** The historical `.deploy_sha` is not a content attestation. Do not claim that the running installation is identical to any GitHub commit based on these data alone. Preserve the old D090 transaction. Do not run `recover` or rewrite the marker while the live state differs from its preimage.

Four isolated tests passed on node104: stable read-only output, symlink fail-closed, marker validation, and divergent retirement evidence. The physical RD6018 was not accessed.
