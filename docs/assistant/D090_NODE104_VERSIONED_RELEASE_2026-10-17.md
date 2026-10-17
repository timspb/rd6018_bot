# D090 — node104 versioned application release transaction

## Scope and result

D090 engineers the offline release trust chain for exact source
`d29db790bf7140932bc005bddf6bd5988041bfc0`, with the observed installed marker
`8b75cca153f00847d84396aba392472bb7552ad` as the required pre-image identity.
It does not reconstruct the old source from local Git: that commit is absent.
The real installed tree must be captured and hashed from node104 in a later,
separately authorized operation.

The supplied local stage is byte-verified: 1003 files, manifest SHA256
`e3fb80039974a72bc0366bab8e21938d7963632610289d67c20f26dfa7fd4b80`, archive
SHA256 `3066e46ccb34b9f1f9712282ff32e15d2c5f6444b8886a481bd5d7c9a3c9ba2d`.
The result is **PREPARE_ONLY_PASS / ACTIVATION BLOCKED**. No node access or
production mutation was performed.

## Trust chain

`tools/node104_d090_release.py` pins source SHA, archive and stage manifest
digests, node hostname/machine ID, service/root, Python 3.11, observed systemd
unit and environment digests, firmware identity, and 900 s / 300 s edge lease
contract. It checks every archive member and the extracted staging tree. The
manifest is immutable in code for this transaction; a future new release must
be a separately reviewed pin, never a SHA argument that silently changes the
target.

Fresh `PhysicalOffProof` is a typed value with host identity, stopped MainPID,
independent HA102 and native ESP128 OFF plus zero V/I, fresh native SensorState,
disarmed edge lease, clear boot quarantine, one owner, no active session, and
distinct source challenge IDs. It expires after 30 seconds. The validator does
not collect evidence or connect to a device. Evidence must be reacquired after
service stop; a pre-stop observation cannot authorize the swap.

The exact Python/ESPHome physical acceptance validator requires matching source
and firmware identity, firmware binary digest, compiled/flashed validation, and
hash-checked artifacts for D061-D065 plus source heartbeat. D089/D088 status,
native API smoke, CI, and a report file alone cannot satisfy this gate.

## Transaction owner and remaining gate

`tools/node104_d090_transaction.py` is the single transaction owner. Its
`D090Transaction` prepare/activate/recover methods run against an injected
service, host check, proof provider, candidate venv builder, and failpoint, so
the complete rename and recovery flow can be exercised under a temporary root.
The production CLI has no SHA override and is deliberately blocked until the
exact firmware digest, installed old-app inventory pin, physical acceptance,
signed-evidence trust root, and independent read-only proof collector digest
are configured and accepted. The command is wired to require a collector file
inside the pinned production root and verify its reviewed digest before use.
This is an
implemented transaction with its real-node command still gated, not an
authorization to operate node104. No node, SSH, service, HA, ESPHome, or
actuator operation was performed for this implementation.

The owner pins source and old SHA through this module, verifies the staged
archive before prepare, checks root/hostname/machine ID on the production host,
and checks the pinned systemd unit and `.env` digests. Physical acceptance and
a fresh pre-stop OFF observation are required before stopping the existing
service. It verifies `MainPID 0`, reacquires a distinct fresh post-stop proof,
then checks that app, venv, state, marker, environment, unit, and stable
independent physical ownership/containment flags still match. Each new
analog V/I sample is independently bounded, not compared bit-for-bit against
previous ADC readings. `PhysicalOffProof` calls
its count `physical_node_owner_count`: it means one independent physical node
ownership source, not one running bot process. The bot process is separately
required to be stopped at the swap boundary.

The old marker alone does not authenticate the installed source bytes. The
executor also requires `PREIMAGE_APP_INVENTORY_SHA256`, a reviewed hash of the
captured installed app inventory. That pin is now `ef24cf5a66abe0991e4e5ceb04988c25806ee9a74d9025ebde00bf3161919171`, captured twice through the pinned read-only node104 SSH route (2026-10-17T07:27:10Z and 07:30:18Z) with identical 1,584-entry file/directory/symlink inventories (1,486 regular files). The prior Git object is still absent locally; production prepare therefore
fails closed even if the marker still says the expected old SHA.

Preparation builds the exact staged app and a separate Python 3.11 candidate
venv, installs the candidate requirements there, and runs compileall plus the
unittest suite in a temporary copy with a synthetic test-only environment; it
does not inherit the operator or service environment. It never installs
requirements into the deployed venv. An exclusive node-local
flock serializes prepare, activate, and recover. Before swap it
creates a metadata-preserving backup of app, venv, state, `.env`, deployment
marker, and unit, verifies a durable inventory, and flushes files/directories.
App and venv move by same-filesystem directory renames. The journal is atomically
written and directory-fsynced at transaction boundaries. On failure,
`recover()` stops and verifies the process is gone, requires fresh OFF evidence,
validates the complete backup against both its digest inventory and pre-image
fingerprints, and restores app/venv/state/configuration. It starts the restored
service only after another fresh OFF proof. Missing or corrupt evidence leaves
the service contained. Completed recovery is idempotent and still checks the
backup inventory.

The service adapter checks systemd active state, MainPID, zero restarts, exactly
one `/proc` bot process, and healthy polling startup logs. The independent
physical proof then checks Output OFF and disarmed lease, while the transaction
compares observer readings before allowing the new marker. Tests use a positive
fake adapter; that is transaction evidence, not physical evidence. Case
artifacts are individually SHA256 checked. No
accepted signature verification key or firmware digest is currently pinned,
so records cannot unlock production by supplying arbitrary metadata.

## Blockers

- Current exact Python source / ESPHome `2.2-autonomous-authority` full D061,
  D062, D063, D064 and D065 physical acceptance is explicitly OPEN in
  `esphome/README.md` and `NODE104_DEPLOY_RESULT.txt`.
- No firmware binary digest paired with this source or trusted physical-record
  signature key is pinned by accepted evidence. The old activator's firmware
  digest is not copied as D090 proof.
- The read-only proof collector SHA256 pin is unset; no external collector is
  trusted to produce fresh physical proof yet.
- No fresh D090 physical OFF proof, host pre-image capture, disk budget, or
  stopped-service transaction evidence exists. D089's prior read-only OFF
  report is stale and cannot authorize a future deployment.
- The installed old-app inventory SHA256 pin is unset; an exact deployed
  `.deploy_sha` marker cannot substitute for the uncaptured source bytes.
- Thus no real-node activation or recovery command is enabled by this prepare
  artifact.
  Coordinator must obtain the applicable physical acceptance and authorize a
  separate node operation after all proofs are current.

## Validation

Focused tests verify exact-stage integrity, tampering, strict boolean/identity
validation, pre-stop versus post-stop evidence, successful fake transaction,
backup digests, staged SHA/host/stale-evidence blocks, secret/observer
preservation, injected journal/swap/start faults, idempotent recovery, and
corrupt-backup containment. These are offline gates, not physical proof.

## Live pre-image read-only binding (2026-10-17)

Two independently executed root read-only walks of installed node104 app
(at 07:27:10 UTC and 07:30:18 UTC) reported the same 1,584-entry
inventory SHA256 `ef24cf5a66abe0991e4e5ceb04988c25806ee9a74d9025ebde00bf3161919171`.
The hash follows the exact `inventory()` canonical JSON digest algorithm,
including permissions and symlink destinations; no file bytes or secrets were
copied or printed. The deployed marker remains `8b75cca1...`, service
PID 59725 NRestarts 0, observer PID 62502 NRestarts 0. Unit SHA256
`74146a925d8c80a6a240f78877e76e060e674f6928f748db43891e7ff1b0e068`
and environment SHA256
`3ca2c77f25c0cde39d5c405114220dc6135197e1f68f3371e9ba8b7ff473a185`
match existing pins. Filesystem free 4,964,286,464 bytes; app 11.59 MB,
venv 250.27 MB, state 28.44 MB and existing backups 152.13 MB.
This closes the pre-image **inventory pin** gap, not full durable backup or
bench/firmware/signed-proof acceptance. Live tree mutation (e.g. pycache)
requires a fresh reviewed hash; do not override digest mismatch.
