# RD6018 V2 ESPHome target

`rd6018_controller_v2.yaml` is the full ESP8266 target for the V2 Pb controller edge contract.
It composes:

- `rd6018_safety_lease.yaml` — 15 minute local dead-man lease, 5 minute bot renewal cadence, direct Modbus freshness and local OFF watchdog;
- `rd6018_telemetry_v2.yaml` — corrected RD6018 telemetry including raw protection register 16 and raw regulation register 17;
- `rd6018_live_adoption.yaml` — positively acknowledged managed->HANDS_OFF release and HANDS_OFF->managed live-adoption primitive.

The repository CI compiles this target with **Python 3.12 + ESPHome 2026.8.2** and publishes the resulting OTA `firmware.bin` as a workflow artifact. This firmware build environment is independent from the bot's production Python 3.11 virtualenv.

## Local configuration

Do not commit real credentials or local network addressing.

```sh
cp esphome/secrets.example.yaml esphome/secrets.yaml
```

Edit `esphome/secrets.yaml` locally and provide the real Wi-Fi, API, OTA and network values. The file is gitignored.

Validate and compile in an isolated Python 3.12 environment using the same ESPHome version as CI:

```sh
python3.12 -m venv .venv-esphome
. .venv-esphome/bin/activate
python -m pip install --upgrade pip
python -m pip install 'esphome==2026.8.2'
esphome config esphome/rd6018_controller_v2.yaml
esphome compile esphome/rd6018_controller_v2.yaml
```

Do not replace or repair the bot's existing Python runtime for this purpose.

## Flash boundary

**Flashing/rebooting this target is not transparent to an active charge.**

Every ESP reboot enters fail-closed boot quarantine. The edge repeatedly requests RD6018 Output OFF until fresh direct Modbus register-18 evidence proves OFF. Therefore do not flash while an external Mix or other load must remain energized.

A successful compile is software validation only. D061/D062 managed live takeover remains forbidden until the target is flashed and exercised on a load-safe bench.

## Required post-flash evidence

Before enabling managed live adoption in production, record all of the following on a dummy/load-safe setup:

1. `Safety Lease TTL` is exactly `900 s` and direct Modbus age is fresh.
2. Raw `Protection Status Code` follows register 16 semantics: `0=NORMAL`, `1=OVP`, `2=OCP`, `3=OPP`; unknown/stale status fails closed.
3. Boot quarantine forces Output OFF after reboot and clears only after fresh direct OFF proof.
4. Normal initial lease arm requires Output OFF; heartbeat renewal while legitimately ON replenishes the lease and increments generation.
5. Managed -> HANDS_OFF live release preserves Output/V/I/OVP/OCP and produces the expected positive generation/state ACK.
6. HANDS_OFF -> managed `Adopt Live Output` preserves Output/V/I/OVP/OCP and produces the expected positive generation/state/remaining-lease ACK.
7. A pre-command generation/TOCTOU race is non-actuating; an actually ambiguous post-command ACK enters verified-OFF containment.
8. Raw-protection loss, out-of-band authority increase, lost lease and process restart all retire authority toward verified Output OFF.
9. Local watchdog expiry at the 15 minute lease boundary forces and re-tries Output OFF without depending on Home Assistant or the bot.
10. D063 prior-age accounting is checked against a known external Mix start time; D062 `MIX_TIMEOUT` and fresh Delta + 2 h terminal paths are physically observed ending in verified OFF.

Only after this evidence is captured may the physical D061/D062 gate be marked PASS. Green Python/ESPHome CI alone does not satisfy that gate.
