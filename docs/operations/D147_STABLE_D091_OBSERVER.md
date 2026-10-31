# D147 — stable read-only D091 observer across application replacement

On 2026-10-31, the live node104 collector differs from the staged candidate D138 collector:

- Actual installed node104 D091 code SHA-256: `1127e9e3ba52a43ca97ddd8501ea4ac9a52887e708d725fd1299fd22d15a2398`.
- D138 staged `tools/node104_d091_physical_proof_collector.py` SHA-256: `a738f08e5554fa70188af856bc359b198838a983394948aaee8c64fdd9df1e95`.

Therefore a proof-collector path inside replaceable `app/` **cannot remain a stable evidence pin** during cutover. D145's physical proof callback MUST NOT silently replace the collector code mid-transaction.

D147 introduces `tools/d147_pinned_collector.py` to create one immutable-by-policy exact copy at `/opt/services/rd6018-bot/d147-proof/node104_d091_physical_proof_collector.py`. It uses the existing D091 collector and has no independent hardware owner or actuator route. It requires the canonical production host identity, verifies the *live* source hash, creates with `O_EXCL`, writes and fsyncs the file and containing directory, and rejects tampering or any group/world-writable path. Existing pins are never overwritten. It never reads credentials, stops a service, or modifies charging settings.

**5/5 node104 isolated tests PASS** (exact byte copy, idempotence, corruption refusal, source drift and symlink/unsafe-directory refusal).

**No production installation or cutover by this PR.** Before using the stable snapshot for release proof collection, verify that it continues to support the D138 candidate runtime APIs and Native ESP state after application replacement; proof must be independently read and checked at each old/stopped/new stage. A collector copy alone does not authorize production cutover or claim post-switch compatibility.
