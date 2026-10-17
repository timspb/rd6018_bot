# D092 — node104 verified-OFF post-stop acceptance (2026-10-17)

## Result and scope

**PASS — fresh independent physical OFF evidence with production service MainPID=0, then restore of the exact prior service.** This closes the D090 **post-stop read-only proof feasibility** milestone only. The D089 application transaction and D065 energized/autonomous bench acceptance were **not** performed.

The approved existing application at the start and end of this verification was `8b75cca153f00847d84396aba392472bb7552ad4`. No source archive, firmware, ESPHome YAML, battery charging recipe, lease TTL, venv, or systemd unit was replaced or updated. The script controlled **only the systemd lifecycle** of the old bot service. While the test orchestrator issued no HA/ESPHome actuator calls, normal bot shutdown/startup hooks could independently perform their existing verified-OFF cleanup and should not be treated as proof of zero physical commands by the bot.

The collector used the SHA256 host-key-pinned node104 SSH path and the D091 read-only installed collector:

- Path: `/opt/services/rd6018-bot/d090/node104_d091_physical_proof_collector.py`
- Accepted SHA256: `c6bf8f456c06da75816976946a9129ccd7619237b6e482874c25a4aa9951ace8`
- Host machine ID: `d2a570f751e14d8cbc654b5c4559ce24`.
- Native ESPHome firmware project version: `2.2-autonomous-authority` (observed identity, not full D065 acceptance).
- Both configured HA102 and native ESP128 provided independent physical register-18 OFF and zero-output measurements.

## Measured physical sequence

The complete on-host automated result is retained in `docs/assistant/D092_NODE104_POSTSTOP_RESULT_2026-10-17.json`. Relevant checkpoints:

| Checkpoint | Epoch time | Service MainPID | HA R18 / V / I | Native R18 / V / I | Lease | Active charge session |
|---|---:|---:|---|---|---|---|
| Before systemd stop | 1792227270.735 | 59725 | OFF / 0.00 V / 0.00 A | OFF / 0.00 V / 0.00 A | Disarmed | None |
| **After service stop** | **1792227273.233** | **0** | **OFF / 0.00 V / 0.00 A** | **OFF / 0.00 V / 0.00 A** | **Disarmed** | **None** |
| After restoring old service | 1792227275.584 | 68224 | OFF / 0.00 V / 0.00 A | OFF / 0.00 V / 0.00 A | Disarmed | None |

At `2026-10-17T08:54:35Z`, the old bot was back `active` with PID `68224`, `NRestarts=0`. The independently running voltage-relaxation observer retained its previous PID `62502` and was not stopped. The deployment marker was unchanged, and there were no `charge_session.json` or `session_recovery_quarantine.json` records.

A second independent SSH and D091 collector observation at `08:58 UTC` reconfirmed the old source marker, `active` bot PID 68224, NRestarts 0, observer still running, no session or quarantine, zero output on HA/native ESP, and a fresh native sensor proof.

## Stopped-service credential and ownership checks

The host's systemd unit specifies `EnvironmentFiles=/opt/services/rd6018-bot/.env`, `Restart=on-failure`, `KillMode=control-group`, `TimeoutStopUSec=90s`. Before the stop, a **read-only names-and-match-only** comparison verified that HA/ESPHome connection variables used by the collector are available in the existing root-controlled `.env` and match the live bot's environment, without copying or printing secret values. The D091 collector autonomously succeeded after MainPID was zero, proving it can obtain independent sensor evidence without depending on the bot process.

## Distinct D065 physical gates still OPEN

1. **Exact-2.2 firmware managed lease Renew -> Disarm smoke** at Output OFF has not been accepted for this new firmware through a suitable, authorized live actuation path. One attempted preparation of a command-bearing smoke harness was blocked by the execution environment before it could be written or sent; do not present that as a tested or failed ESPHome behavior.
2. **Exact-2.2 autonomous enter/exit smoke** under verified-OFF bench conditions remains open.
3. **Output ON beyond 900 seconds without HA/Wi-Fi** in AUTONOMOUS mode requires an independently isolated, current-limited, supervised safe bench load, not an attached customer battery.
4. **ESP-only reboot while Output ON** in autonomous mode and managed boot-quarantine behavior require their own controlled bench isolation and emergency OFF control.
5. **D064 raw protection/thermal injection, torn persistence, firmware binary digest, and signed exact-source D061–D065 evidence** remain open as stated in the canonical firmware runbook.

The node104 RD6018 reported battery voltage approximately **13.06 V** while the output remained disabled, consistent with a battery connected at the terminals. There is **no positive evidence of an electrically isolated safe test load** in the acceptance record. Do not substitute the battery for a sacrificial bench load or energize Output to satisfy tests 3–5.

The D090 production activation must therefore continue to refuse `activate` until exact-source physical gates have genuinely passed. Do not replace, weaken or synthesize bench/firmware acceptance or signer pins. The user has authorized engineering; the remaining condition is the technical proof, not an additional administrative permission.

## Status

- D091 deployed read-only collector: **PASS**.
- D092 verified physical post-stop proof and restoration: **PASS**.
- D065 OFF-only command smoke: **NOT RUN**.
- D065 energized/autonomous physical suite: **NOT RUN**.
- D089/D090 atomic production swap: **NOT RUN; intentionally gated**.
- Existing deployed bot and D063 relaxation observer: **healthy**, with proof after restoration.
