# D088 — node104 / D087 physical read-only preflight (2026-10-17)

## Acceptance classification

**READ-ONLY PHYSICAL PREFLIGHT: PASS. D087 LIVE ACCEPTANCE / DEPLOYMENT: NOT RUN.**

This report records a fresh node104 observation against the accepted software
main `0b28ef7e435f29f95a3291cf6cbc80149acef668`. It must not be
misread as D087 hardware acceptance: the node104 application is on an older
deployed source. There were **no RD6018/ESPHome actuator commands, ON/OFF
writes, lease button operations, service restarts, filesystem uploads or
production deployment**.

## Identity, provenance and service

- SSH established through the already configured Windows-to-node104 Paramiko
  profile. SHA256 host-key fingerprint matched the existing pinned profile
  **and** known_hosts. No host-key enrollment or trust bypass.
- Remote UTC sample: `2026-10-17T06:17:32Z`.
- Host `rd6018-bot`, machine ID
  `d2a570f751e14d8cbc654b5c4559ce24`.
- `rd6018-bot.service`: ACTIVE/RUNNING, PID `59725`, `NRestarts=0`,
  active since 2026-10-14 14:27:45 UTC.
- The optional `rd6018-voltage-relaxation.service` remains ACTIVE,
  PID `62502`, NRestarts=0.
- Production `.deploy_sha`: `8b75cca153f00847d84396aba392472bb7552ad4`.
  This is **not** the accepted D087 main, `0b28ef7e435f29f95a3291cf6cbc80149acef668`.
  `runtime/ui/telegram/recovery_clearance.py` is absent on production.
- Canonical production `charge_session.json` and
  `session_recovery_quarantine.json` were both absent at observation time.
  No identity or telemetry was synthetically filled in.

## Independent physical state evidence

A diagnostic process read the existing bot's environment **in memory only**
(no secrets printed, persisted or changed) to establish both configured
transport connections. It used the installed HA102 and native ESP128
`get_live_values()` read APIs; ESPHome `discover()` and subscriptions
performed only reads. A first probe without the service environment failed
configuration validation; after correcting the invocation, **both sources
returned success**.

| Evidence | HA102 | Native ESP128 |
|---|---:|---:|
| Output State Code (R18) | 0 / OFF | 0 / OFF |
| Voltage / current | 0.00 V / 0.00 A | 0.00 V / 0.00 A |
| Battery voltage | 13.06 V | 13.06 V |
| Vset / Iset | 13.57 V / 0.10 A | 13.57 V / 0.10 A |
| OVP / OCP | 14.07 V / 0.20 A | 14.07 V / 0.20 A |
| Protection code | 0 / NORMAL | 0 / NORMAL |
| External / internal temp | 23 / 28 °C | 23 / 28 °C |

Native register-18 source type was `SensorState`; `_meta` reported
`status=ok`, `age_s=0.0` at the corresponding sample. This proves
a fresh read-only OFF state, not a post-command OFF receipt for the new
D087 transaction.

Native ESPHome edge read-only values (age under 4 seconds at sample):
`edge_lease_armed=false`, `edge_lease_tripped=false`,
`edge_boot_quarantine=false`, `edge_lease_remaining=0`,
`edge_lease_generation=55`, `edge_modbus_age≈2.366 s`.
Buttons were **read only as inventory** and never pressed.

Configuration readiness (without disclosing numeric Telegram IDs):
one explicit positive `ALLOWED_CHAT_IDS` entry, `ALLOW_ALL_CHATS=false`,
`V2_UI=true`, `RD6018_EDGE_LEASE_REQUIRED=true`.
This establishes configuration prerequisites, not a D087 command/nonce test.

## Exact-source offline staging

The project `tools/node104_atomic_deploy.py stage` was run **locally in
WSL2**, not on node104. The staging release for exact SHA
`0b28ef7e435f29f95a3291cf6cbc80149acef668` contains **1001 files**.
Its manifest SHA256 is
`e224aed068d7c2a033d0efe4327da88a015e47977d1b9184b516acac67071a8d`.
The staging verifier reported `tree_verified=true` and
`directory_fsync=true`. Local source worktree was clean.

The canonical staging tool is **not** a production activator. Its deployment
preflight explicitly requires fresh independent evidence of the service already
stopped, Output OFF / zero output, edge containment, correct firmware and
verified filesystem topology. This run did **not** stop the service and did not
claim the corresponding preflight or activation gate PASS.

## Remaining acceptance gates

1. Prepare and prove a **separate, bounded, rollback-capable production
   deployment** for the whole source delta from installed
   `8b75cca1…` to `0b28ef7e…` — not an ad-hoc D087-only file copy.
2. With fresh pre/post independent source observations, stage/review service,
   persisted state, firmware compatibility and restored source provenance;
   preserve production data and observer ownership.
3. On an approved isolated acceptance scenario, exercise the **installed D087**
   `/recovery_clear` flow: private whitelist + short-lived nonce; matching
   durable incident and session; **post-command** native R18 OFF receipt;
   crash-safe session retirement; journal tombstone; reboot with no
   unexpected automatic Output ON.
4. Test fail-closed cases (stale/offline source, mismatched identity,
   unknown schema, cancelled operator action, write/fsync failure) without
   energizing an unattended battery.
5. Preserve edge lease 900-second TTL and 300-second renewal, and all
   independent verified emergency OFF paths. Do not assert physical PASS
   from software-only tests.

No additional human privilege registry is required: the configured explicit
Telegram allowlist already exists. The open gate is deployment/physical
verification, **not user permission**.

## Evidence collection paths

Host-owned diagnostic scripts, containing no new credentials:
`E:\CODEX\rd6018_d087_node104_verified_ro_20261017.py`,
`E:\CODEX\rd6018_d087_live_dual_readonly_20261017.py`,
`E:\CODEX\rd6018_d087_auth_readiness_ro_20261017.py`.
Local offline staging:
`/tmp/rd6018-d087-20261017-staging`.
No private key, token, chat ID, or raw environment was copied into this report.
