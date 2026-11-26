# B1023 — source-paired D145/D124 readiness

**Result: BLOCKED for D124 profile admission; source candidate prepared offline.**
**Physical/release acceptance: HOLD. No deployment is authorized or performed.**

## Candidate source facts

- Candidate source: `a5364c8cdc2e062a91aaef9861b1dd39e137fd91`.
- Existing offline `node104_atomic_deploy.stage` produced and verified a
  schema-3 source manifest, `STAGED_OK` marker, extracted tree, and archive in
  `/tmp/rd6018-b1023-source-pair/release-a5364c8cdc2e062a91aaef9861b1dd39e137fd91-bafmkme0`.
- Tracked file count: 1,759.
- Source archive SHA-256: `5b4d9c3687c3168c7d07cb200dcc39be54f7b632e538e4f8d70d1694f03e4f7f`.
- Serialized stage manifest SHA-256: `f390fdb839b52ee4d6aca78ed8e1995f2a6cdec6ac30834def1687bc9fbb2c2c`.
- This generic offline stage is a verified source archive/tree only. It is not
  a D138 app+venv candidate, D137 installed preimage, or D145 admission.

## D124/D145 assessment

`tools/node104_d124_release_profile.py::load_software_release_profile` uses
the existing schema-2 profile. A complete profile needs exact old and new
source identities, current node/service identity, installed Python and
firmware identity, source archive/manifest, installed preimage inventory,
changed-path classification, service unit and `.env` metadata, and proof
collector identity. Candidate source/archive/manifest values above are
independently reproducible from the tracked checkout. The old installed
identity and remaining node-specific values cannot be inferred from historical
D146 files or checkpoint text.

`tools/node104_d145_entrypoint.py` is pinned to historical D146 profile bytes,
source `d351c208cbf8666f881a4660df6a0b211170e857`, preimage inventory
`9651e979e6394fd53ee373010f845ba00e7ccbbfa85a7a313b95893a0edea444`, and
the historical observer contract. It cannot admit this candidate. Do not
change those pins to make the candidate pass. Candidate pairing must preserve
the existing D090 transaction and D144 owner, and use a specifically reviewed
source-paired D145 tool/profile set after actual node observations are
available. D147/D150/D151 are distinct tracked observer versions; D149 routes
by phase. Tracked expected digests are not proof that the matching artifacts
are installed on node104.

The JSON skeleton at
[`B1023_SOURCE_PAIR_PROFILE_SKELETON.json`](B1023_SOURCE_PAIR_PROFILE_SKELETON.json)
contains only the exact candidate-side source values and explicit
`NOT VERIFIED` markers for missing inputs. It is intentionally not a valid
D124 release profile and must not be used with `prepare`, `execute`, or
`recover`.

## Required observations before completing the profile

Collect through the existing authorized read-only owners; do not alter node,
service, ESP, HA, or controller state during this source-only preparation:

1. Fresh direct ESP Native subscription and device identity; firmware version,
   R18, measured U/I, battery voltage, Vset/Iset, raw R16, lease state and
   Modbus age, trip/quarantine/autonomous state. Historical reports are not
   current evidence. R16=1/2 remain diagnostic/operator-manageable only;
   R16=3 and unknown nonzero remain fail-closed. No OVP/OCP threshold writes.
2. Current D144 installed release ledger/identity and exact installed app plus
   venv composite inventory, with running process/service identity; do not use
   the old D146 preimage as a substitute.
3. Exact current systemd unit and `.env` metadata, recorded without disclosing
   secrets; installed Python interpreter/version and service environment
   source.
4. Exact collector files/version that the D149 phase router will use
   (D147 for PRE_STOP, D151 for state-preserving STOPPED/POST_START/RECOVERY
   under the current entrypoint), plus confirmation that the corresponding
   artifacts are present at the expected node paths. Do not treat tracked
   digests as installed observations.
5. D138 candidate app+venv stage for this source. The current generic offline
   source stage contains no candidate venv and is insufficient for D138.
6. Compare the observed installed source to this candidate to derive the
   exact `changed_paths`; D124 must classify it as Python control only with no
   firmware paths. Then populate the existing schema-2 D124 profile and run
   its loader fixture. Keep D145 historical pins untouched until the exact
   source/tool/profile pairing is independently reviewed.

After an approved read-only collection provides these inputs, the first
offline completion command is:

```bash
PYTHONPATH=.:tests:tools /home/home-pc/.venvs/pcp-test/bin/python - <<'PY'
from pathlib import Path
from tools.node104_d124_release_profile import load_software_release_profile

profile = Path("docs/acceptance/B1023_SOURCE_PAIR_PROFILE_SKELETON.json")
pin, preimage, record = load_software_release_profile(profile)
print(pin.source_sha, preimage, record["mode"], len(record["changed_paths"]))
PY
```

This command is expected to fail on the present skeleton. Only run after all
`NOT VERIFIED` fields have been replaced from current, independently captured
evidence. D124 schema acceptance alone is not D145 admission or physical
release acceptance.



## Controller reconciliation — avoid self-referential source/profile SHA

This report captures an offline test of the **historical B1023 task base**
`a5364c8cdc2e062a91aaef9861b1dd39e137fd91`, not the now newer
feature-branch HEAD. The tracked JSON skeleton is **intentionally INVALID
and source-neutral**: source SHA, source archive and staged-manifest SHA are
marked NOT VERIFIED. A source-paired profile containing its own current
archive SHA cannot safely be pinned inside the same tracked release archive
because that would change the source SHA again. After all code and release
docs are frozen, generate the complete source-paired profile as a
**separate out-of-tree acceptance artifact**, using independently observed
node104 preimage, service, firmware and collector identity; do not repin the
historical D145 profile or mistake an offline skeleton for admission.
