# D106 — live-observer integration, offline rollback gates, and D097 disposition (2026-10-18)

## Acceptance classification

**SOFTWARE BRIDGE: PARTIAL PASS — SOURCE ONLY. D097_PHYSICAL_OPEN. PRODUCTION UNCHANGED.**
Starting authority: merged main `9a16a26104c1b049aa4ca9cc660670cf02cdc0cf`.
Reviewed trial source: `b3cd0174a2918dbbc2ee3f9c908fa14d15089a29`.
Permanent D090 pins, firmware digest and physical-signer trust root were NOT changed.
No new service, Telegram poller, release owner, entrypoint, physical controller, systemd drop-in, firmware change or Output operation was added.

### D105 staged artifact

`E:\\CODEX\\RD6018_D105_REVIEW_STAGE_b3cd0174a291` independently rechecked using D102 `verify_source(stage, pin=TRIAL_PIN)`:
source commit `b3cd0174a2918dbbc2ee3f9c908fa14d15089a29`;
source tar SHA256 `410af38f6a8ec059560aa1bc351b00a572a96121c3d93a216cbe86a433e84ae4`;
manifest SHA256 `f9c5725638b77a6e76e52cb7269b2e95f1fdbeda8b442d6c6b9811e347947575`;
**1027/1027 PASS**. Prior Python 3.11 offline wheelhouse tar independently SHA256-verified:
`ddba53a5d352756ec678dd47ccf2d891b66ffc4c00a32287cef47dc2d1df9442`.

### Source changes (offline only)

- `tools/node104_d090_transaction.py`: `SystemdService.stable_trial(TRIAL_SOURCE_SHA)`
  checks the separate trial pin, deployed marker, service process and zero restarts;
  journal validation is owned separately by the locked D090 recovery path.
  Ordinary `stable()` still allows ONLY D090 permanent release pins.
  No live begin/finish CLI added. Existing `_trial_gate()` remains offline-only for activation.
- Independent `_trial_recovery_gate()` permits journal-pinned **recovery**, NOT
  candidate activation, without an enablement socket or activation permission.
  Recovery still insists on fresh physical OFF and edge proofs, source/host/pin,
  backup inventory, same-file-system restoration and exact old preimage.
  Additional failpoints: after app/state/venv restoration, after configuration/marker,
  immediately before old bot restart. The exact source of service stop/restore
  and journal authority remains `D090Transaction`.
- `tools/node104_d106_readonly_projection.py`: strict HA REST + native ESP
  observation contract. Require actual independent, fresh HA autonomous state.
  HA102 source owns register-18, voltage/current, R16, setpoint/protection and
  autonomous; the lease/TTL/remaining/Modbus age are native-only fields
  (not fictional HA entities). Missing, unknown, contradictory, stale, wrong
  callback type or ButtonInfo cannot become a positive observation.
- `tools/node104_d106_live_observer.py`: source-only read adapter for the
  existing D091 on-node typed physical transports; does not install itself.
  HA values must come from HA REST last_reported and native values from typed
  ESP128 callbacks. It does NOT inject fake values or expose actuator calls.
- `tools/node104_d106_readonly_socket.py`: only sends canonical
  `autonomous_status`; validates root-owned socket mode 0600, live peer
  UID/PID, bounded success receipt, PB_MANAGED, OFF/R16=0, programmed values
  and lease. It does not support enter/exit. The actual status socket is
  opt-in and presently not admitted as a D106 temporary release lifecycle.

### Tests

- Focused D105 before change: **27/27 PASS**.
- D106 read-only + recovery tests after HA/native ownership correction:
  **41/41 PASS** (includes inherited D105 fixtures).
- Full Python 3.12 project-venv suite after first bridge patch:
  **2209 OK, 2 skipped**. Synthetic nonproduction config variables
  were used after the initial run without test TG_TOKEN failed at imports.
- A subsequent full-suite invocation **after the final live observer file**
  was rejected by the HOME-PC tool with the exact message
  `Этот вызов инструмента был заблокирован системами безопасности OpenAI`.
  It was **not rerouted through another execution channel**.
  Therefore final-tree full suite and CI 3.10/3.11/3.12 are **NOT yet attested**.
  The newer live observer has syntax compilation PASS, not on-node runtime proof.

### Fresh node104 read-only observation

Via existing Windows-to-node104 Paramiko route, independent pinned SSH
host fingerprint plus known_hosts validation PASS. Timestamp of service
identity read: **2026-10-17T15:57:36Z**; source marker `8b75cca153f00847d84396aba392472bb7552ad4`,
hostname `rd6018-bot`, machine-id `d2a570f751e14d8cbc654b5c4559ce24`.
Service `rd6018-bot.service` active, MainPID **69648**, NRestarts **0**;
voltage relaxation observer PID **62502**, also active; no session file
or quarantine state document. Read-only native/HA diagnostic:
HA and native R18 OFF; voltage/current 0.00 V / 0.00 A;
Protection R16=0; Vset 13.57 V, Iset 0.10 A;
OVP 14.07 V, OCP 0.20 A; battery voltage about 13.06 V.
Native edge `lease_armed=false`, `remaining=0`,
`boot_quarantine=false`, `lease_tripped=false`;
native Modbus age approx. 3.90 s. The diagnostic's
`ButtonInfo` entries reported unknown and were **not** used as states.

This live check did **not** collect a fresh HA `autonomous_mode`
last_reported, native `safety_lease_ttl`, complete current original-app
inventory, systemd drop-in preimage and D090 journal identity in one
atomic proof. It also does not attest to exactly one Telegram poller
across all potential hosts. Hence **FULL D106 LIVE ADMISSION OPEN**;
the observer source is not claimed physically verified.

### Physical and release decisions

`D097_PHYSICAL_OPEN`. No D097 status/enter/exit occurred during D106;
no trial installed; physical-test socket was not enabled.
No service restart, stop, copy, swap, drop-in or candidate activation
was attempted. No physical controller command or firmware change.
The existing production preimage was left in place (no restore required).

Release/physical blocker: exact 8b75 preimage and temporary socket/drop-in
rollback lifecycle still need independent live review and crash matrix
acceptance; source-only observer must be tested against the real installed
HA/native contract, including HA autonomous freshness; exact trial running
identity, logs and one Telegram poller must be proven; edge transitions
must be durably journaled through the D090 owner with post-enter
AUTONOMOUS/disarmed lease evidence and >=10 s dwell before exit.
An unsealed backup must NEVER count as durable restoration material.
D061–D065 energized/reboot/outage gates stay separate and open.

Do not remove the D105 offline trial activation gate or modify production
until the above is independently proven and final full suite/CI pass.
