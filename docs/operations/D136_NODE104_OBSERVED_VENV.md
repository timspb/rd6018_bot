# D136 — observed node104 Python environment baseline

Read-only observation on 2026-10-31. This is **not an admission or reconstruction of the D090 historical candidate**.

The observer `tools/d136_observed_venv.py` was run on node104 with the positively identified bot process PID 162141. Two consecutive inventories were identical; the D090 transaction journal and deploy-marker digests remained unchanged throughout the scan.

| Field | Observed value |
|---|---|
| venv inventory entries (directories, links, files) | 10175 |
| venv regular files | 9335 |
| venv symlinks | 4 |
| venv tree SHA-256 | `17797cd36bea1633c6ff6efda05e4ab8c450d9369c12cec828f30217c4d72cf5` |
| live app tree SHA-256, from D133 | `691e3ffd0b612d6832e8cd95030196f42ac384138c68ffd6b1e3545d85afd669` |
| D090 journal SHA-256 | `030f0b7aae43402f523bb57f5acd606e3ab2fe4f7c7d4efd40258b40bde8014e` |
| deploy marker SHA-256 | `0d96a7d51ad6216a5c7bd12b1987a1c2ca5468f2facc8fd1f497e4260787632f` |
| D090 transaction | `818df047a6e64a22905d6da900162a86`, `STARTED`, `candidate_inventory` absent |

The venv tree hash is computed over lexicographically sorted relative paths, entry type, file length, executable bit, content SHA-256 and a hash of each symlink target. The tool does not print secrets or follow symlinks. D136's four isolated unit tests ran **4/4 PASS** on node104.

**Critical boundary:** These are *observed live bytes*, not preserved build artifacts. D090's missing candidate venv provenance remains unresolved. D136 does not authorize modifying journal phase, `.deploy_sha`, service unit, installed software, state, device Output, settings or 900-second lease. No replay of old D090 `recover` is allowed for ledger cosmetic cleanup.

This observed composite app+venv baseline can be used for future read-only drift comparisons and as input to a separate owner-reviewed new release transition. It cannot be used to pretend that `930239c` has been fully reconciled with its original generated venv.
