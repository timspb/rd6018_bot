# RD6018 V2 ESPHome firmware

This directory is the canonical firmware source and build/install runbook for the
RD6018 edge used by the Pb Recovery V2 controller.

The repository contains **no production Wi-Fi, Home Assistant API, OTA or network
secrets**. Production secrets live only in the operator's local
`esphome/secrets.yaml`, which is gitignored.

## Canonical layout

```text
esphome/
├── rd6018.yaml                         # only Device Builder node
├── packages/
│   ├── rd6018_safety_lease.yaml       # 15 min dead-man + boot quarantine
│   ├── rd6018_telemetry_v2.yaml       # corrected RD6018 telemetry
│   └── rd6018_live_adoption.yaml      # HANDS_OFF release/live adoption
├── secrets.example.yaml               # dummy/example values only
├── build_firmware.sh                  # canonical reproducible CLI build
└── README.md
```

The package YAML files deliberately live below `packages/`. When this layout is
copied into Home Assistant's `/config/esphome`, Device Builder sees `rd6018.yaml`
as the device and does not present each package as a separate offline node.

The node identity remains:

```text
rd6018-controller
```

The target is ESP8266 `esp01_1m`, RD6018 Modbus address `1`, UART
`GPIO1/GPIO3 @ 115200`, and a 5 second Modbus polling interval.

## Edge contract included in this firmware

The firmware composes three safety packages:

- `rd6018_safety_lease.yaml`
  - exact local dead-man TTL: **900 s / 15 min**;
  - initial arm requires fresh direct Output OFF evidence;
  - managed heartbeat may renew while Output is legitimately ON;
  - stale control evidence or lease expiry latches a trip;
  - the edge retries RD6018 Output OFF every 5 seconds after trip;
  - every ESP reboot enters boot quarantine and repeatedly requests Output OFF
    until fresh direct register-18 evidence proves OFF;
  - ordinary Disarm is verified-OFF only;
  - managed -> HANDS_OFF release is a distinct Output-preserving transaction.

- `rd6018_telemetry_v2.yaml`
  - register 16 is exposed as the authoritative protection status code
    (`0=NORMAL`, `1=OVP`, `2=OCP`, `3=OPP`);
  - register 17 is exposed as the regulation mode code (`0=CV`, `1=CC`);
  - output power is read from register 13 as one `U_WORD`;
  - internal/external temperatures use the RD6018 sign+magnitude register pairs;
  - critical stable telemetry/status sources used for V2 freshness publish unchanged
    samples to Home Assistant (`force_update`), so a numerically stable value still
    has a current source heartbeat;
  - register 18 is additionally exposed as read-only `Output State Code V2` with
    `force_update`; the public `Output` switch remains the actuator endpoint while
    this read-only mirror supplies canonical Output value/freshness evidence to V2;
  - calibration registers are read-only diagnostics.

- `rd6018_live_adoption.yaml`
  - publishes the actual configured lease TTL;
  - provides `Safety Lease Adopt Live Output`;
  - adoption is refused unless the local TTL is exactly 900000 ms;
  - adoption requires fresh direct Modbus, Output ON and raw protection NORMAL;
  - successful adoption changes only ownership/lease state and does **not** write
    Output, voltage, current, OVP or OCP.

`rd6018.yaml` also preserves the Home Assistant entity names used by the bot.

## 2026-09-03 source-heartbeat correction

The first real bot-level D061 preflight exposed a distinction between **RD Modbus is
fresh** and **each HA entity has a fresh source report**. During an external HANDS_OFF
program the physical edge reported approximately:

```text
Safety Modbus Age ~0.9 s
Protection Status Code = 0
Regulation Mode Code = 1
```

but the bot correctly rejected acquisition because the unchanged battery-voltage HA
entity had aged beyond the V2 safety limit:

```text
battery_voltage stale age=45.2s>20.0s
```

The 20 s fail-close is intentionally **not** widened. Instead, the canonical firmware
now publishes unchanged critical observations as source reports:

- `Output voltage` register 10: `force_update: true`;
- `Output current` register 11: `force_update: true`;
- `Battery voltage` register 33: `force_update: true`;
- `Protection Status Code` register 16: `force_update: true`;
- `Regulation Mode Code` register 17: `force_update: true`;
- corrected internal/external V2 temperature templates: `force_update: true`;
- new read-only `Output State Code V2`, register 18: `force_update: true`.

The public Home Assistant Output switch is still the write/actuator entity. The bot
uses `Output State Code V2` only as the canonical read-only Output value/freshness
source when it exists. Missing, invalid or stale evidence remains fail-closed.

This source-heartbeat change does **not** modify `rd6018_safety_lease.yaml`, the
900 s TTL, the 300 s bot renewal interval, lease expiry logic or boot quarantine.
Therefore the already-completed 900 s physical watchdog tests do not need to be
repeated solely because of this telemetry publication correction.

Code-bearing commit `28dd548bfddbb4a4913a1fd64be26c7bd3ededfa` passed exact-head:

```text
CI #1091                 SUCCESS
ESPHome firmware #29     SUCCESS
```

Those results prove software/compile validity only. The corrected firmware must still
be built with local production secrets, flashed at a safe interruption point and
physically checked before the corrected D061 source-heartbeat path can be called a
physical PASS.

## Supported build environment

The firmware build is pinned to:

```text
Python:  3.12+
ESPHome: 2026.8.2
```

This build environment is independent from the bot's production Python runtime.
Do not replace or repair the bot interpreter merely to compile ESPHome.

The GitHub Actions workflow and the local build both call the same
`esphome/build_firmware.sh` script.

## Secrets

Create a local file:

```sh
cp esphome/secrets.example.yaml esphome/secrets.yaml
```

Edit **every** value in `esphome/secrets.yaml`.

Required keys:

```yaml
rd6018_wifi_ssid: "..."
rd6018_wifi_password: "..."
rd6018_fallback_ap_password: "..."
rd6018_api_encryption_key: "..."
rd6018_ota_password: "..."
rd6018_static_ip: "..."
rd6018_gateway: "..."
rd6018_subnet: "..."
```

`esphome/secrets.yaml` is gitignored. Do not commit it, paste it into issues/PRs,
or upload a production-built firmware binary as a public artifact: the compiled
firmware contains local credentials.

The committed `secrets.example.yaml` contains dummy values and RFC 5737 example
addressing only.

## Reproducible local build

From the repository root on Linux/macOS with Python 3.12 available:

```sh
cp esphome/secrets.example.yaml esphome/secrets.yaml
# edit esphome/secrets.yaml first

./esphome/build_firmware.sh
```

The script:

1. requires a local `secrets.yaml`;
2. creates/reuses `esphome/.venv`;
3. installs exactly ESPHome `2026.8.2`;
4. runs `esphome config esphome/rd6018.yaml`;
5. compiles the target;
6. copies the OTA image to:

```text
esphome/dist/rd6018-controller-v2.bin
```

7. prints its SHA-256 when `sha256sum` or `shasum` is available.

Validation without compiling:

```sh
./esphome/build_firmware.sh --validate-only
```

Override the Python executable or venv only when necessary:

```sh
PYTHON=/usr/local/bin/python3.12 \
ESPHOME_VENV=/tmp/rd6018-esphome-venv \
./esphome/build_firmware.sh
```

## CI build

`.github/workflows/esphome.yml` runs on firmware changes.

CI uses:

```sh
ESPHOME_SECRETS_MODE=example ./esphome/build_firmware.sh
```

That mode is deliberately safe:

- it works only when no real `esphome/secrets.yaml` exists;
- it temporarily copies `secrets.example.yaml`;
- the temporary secrets file is removed on exit;
- the resulting GitHub artifact contains **dummy CI credentials**.

Therefore a CI artifact proves that the source compiles, but it is **not a
production OTA image** for a real node. For production, compile locally with the
real local `secrets.yaml` or use Home Assistant Device Builder.

## Home Assistant Device Builder installation

Recommended production path.

### 1. Back up the existing working configuration

On Home Assistant OS/SSH:

```sh
cd /config/esphome
cp -a rd6018.yaml rd6018.pre-v2.yaml.bak
cp -a secrets.yaml secrets.pre-v2.yaml.bak
```

Use the actual existing filename if it differs.

### 2. Copy the canonical source layout

The final Home Assistant layout must be:

```text
/config/esphome/
├── rd6018.yaml
├── packages/
│   ├── rd6018_safety_lease.yaml
│   ├── rd6018_telemetry_v2.yaml
│   └── rd6018_live_adoption.yaml
└── secrets.yaml
```

Do **not** place the three package YAML files directly in `/config/esphome/`;
Device Builder may show them as separate offline devices.

Do not overwrite an existing `secrets.yaml` with `secrets.example.yaml`. Add the
required `rd6018_*` keys to the local secrets file instead.

### 3. Validate before flashing

In ESPHome Device Builder:

```text
RD 6018 -> menu -> Validate
```

The build must report the expected ESPHome version and a valid configuration.

CLI equivalent:

```sh
esphome config /config/esphome/rd6018.yaml
```

### 4. Flash wirelessly

Only when interrupting RD6018 Output is safe:

```text
RD 6018 -> Install -> Wirelessly
```

The ESP reboots during OTA. This firmware intentionally enters boot quarantine,
so flashing is a session-interrupting operation, not a transparent update.

CLI equivalent, when ESPHome CLI is available in the environment:

```sh
esphome upload /config/esphome/rd6018.yaml --device <ESP-IP>
```

If a production binary was already built locally:

```sh
esphome upload /config/esphome/rd6018.yaml \
  --device <ESP-IP> \
  --file /path/to/rd6018-controller-v2.bin
```

`--file` uploads that exact binary instead of the most recent local build.

### 5. First USB installation

For a blank/recovery ESP, use ESPHome Device Builder / ESPHome Web with a serial
connection and the locally built production firmware. Once ESPHome OTA is
installed and network credentials are correct, later updates can be wireless.

## Mandatory flash safety boundary

**Never flash/reboot while an external charge, Mix session or other load must
remain energized.**

On every reboot:

```text
ESP boot
  -> boot quarantine
  -> repeated RD6018 Output OFF requests
  -> fresh direct Modbus register-18 OFF proof
  -> quarantine clears
```

This is deliberate fail-closed behavior.

## ESP-only reboot validation caveat

Do not use a same-image OTA flash merely as a substitute for an independent ESP
restart test on the currently deployed node.

The stronger reboot-containment proof requires:

```text
RD6018 remains powered
Output initially ON
only ESP8266 restarts
boot quarantine drives RD6018 Output OFF
fresh register-18 OFF proof clears quarantine
```

Two common shortcuts are not valid evidence:

- power-cycling RD6018 also removes the source of Output, so it cannot isolate the
  ESP boot-quarantine action;
- on the physically deployed node, the operator observed that after an OTA flash
  the ESP enters its captive/fallback Wi-Fi path and asks for Wi-Fi connectivity to
  be re-established/confirmed. That additional network-state transition means OTA
  is not a clean ESP-only reboot injection for this bench claim.

Keep the ESP-only reboot gate pending until a clean independent reset/restart path
is available while RD6018 remains continuously powered. This does not invalidate
the normal post-flash boot-quarantine smoke evidence already observed.

## Post-flash smoke gate

Before connecting a battery or enabling a managed charge, verify in Home Assistant:

```text
Safety Lease TTL             = 900 s
Safety Lease Armed           = OFF
Safety Lease Remaining       = 0 s
Safety Lease Tripped         = OK/OFF
Safety Boot Quarantine       = OK/OFF after fresh OFF proof
Safety Modbus Age            fresh (well below 20 s)
Protection Status Code       = 0 / NORMAL on an idle healthy RD
Output State Code V2         = 0 while Output OFF
Output                        = OFF
```

Also confirm that these entities exist:

```text
Safety Lease Renew
Safety Lease Disarm
Safety Lease Release To Hands Off
Safety Lease Adopt Live Output
Protection Status Code
Regulation Mode Code
Output State Code V2
Temperature Internal V2
Temperature External V2
Output Power V2
```

For the 2026-09-03 source-heartbeat correction, keep the values stable for at least
30-60 seconds and inspect HA source timestamps. `last_reported` for the critical
V2 sources used by the bot should continue advancing at roughly the 5 s Modbus/update
cadence rather than aging past 20 s merely because the numerical value did not move.
At minimum verify this behavior for battery voltage, output voltage/current, raw
protection/regulation, corrected temperatures and `Output State Code V2`.

### Verified-OFF arm/disarm smoke test

With Output confirmed OFF and no battery/load requiring power:

1. press `Safety Lease Renew`;
2. verify Armed=ON, Generation increments and Remaining starts near 900 s;
3. verify Output remains OFF;
4. press `Safety Lease Disarm`;
5. verify Armed=OFF, Remaining=0, trip/quarantine remain clear and Output remains OFF.

## Full physical acceptance gate

A successful compile and the smoke test above do not by themselves authorize the
complete D061/D062 bot workflows. Current physical status is tracked explicitly:

- [x] exact 15 minute edge watchdog expiry and autonomous local Output OFF;
- [x] verified-OFF trip latch recovery through Disarm;
- [x] managed -> HANDS_OFF release preserving Output/V/I/OVP/OCP;
- [x] HANDS_OFF -> edge live adoption preserving the running program;
- [x] adopted lease expiry -> autonomous local Output OFF;
- [x] live-adopt command rejected while Output is already OFF;
- [x] first real bot D061 preflight rejected stale HA battery-voltage source evidence read-only, before any edge command or actuator write;
- [ ] corrected force-updated source heartbeat + `Output State Code V2` physically deployed/verified;
- [ ] full bot D061 positive takeover after the corrected firmware/bot pairing;
- [ ] ESP-only reboot with RD continuously powered and Output initially ON;
- [ ] bot-side pre-command TOCTOU rejection on real hardware;
- [ ] ambiguous command/ACK containment on real hardware;
- [ ] raw-protection loss/non-NORMAL injection;
- [ ] out-of-band authority increase forcing verified OFF;
- [ ] complete bot-runtime downward ratchet/Stop/restart containment;
- [ ] D063 prior-age accounting against a known external session start;
- [ ] full D062 `MIX_ADOPTED` takeover through the bot;
- [ ] physical D062 `MIX_TIMEOUT` and fresh Delta+2h terminal OFF paths.

Only recorded physical evidence may close those gates.

## Current physical status

As of the original 2026-09-02 flash, the canonical V2 firmware is physically installed
on the target ESP8266/RD6018 and the edge-level safety/ownership primitives have real
bench evidence:

- ESPHome 2026.8.2 node returned online after production OTA;
- `Safety Lease TTL = 900 s`;
- raw protection/regulation V2 entities are present and readable;
- boot quarantine cleared only after fresh direct Output OFF proof;
- verified-OFF arm/disarm works;
- a lease allowed to expire at 900 s latches trip;
- with the RD6018 physically energized on a safe battery-disconnected bench, the
  same expiry autonomously drove Output voltage/current to zero;
- late recovery did not silently resume the old lease; verified-OFF Disarm cleared
  the trip;
- `Release To Hands Off` preserved an energized safe program and removed the lease
  without changing Output/V/I/OVP/OCP;
- `Adopt Live Output` successfully acquired an already-running safe program with
  raw protection NORMAL, armed the 900 s lease and preserved Output/V/I/OVP/OCP;
- expiry of that adopted lease autonomously drove Output OFF;
- pressing `Adopt Live Output` while Output was OFF left Armed OFF, Remaining 0,
  Generation unchanged and Output OFF.

On 2026-09-03 the first real bot D061 preflight with a connected Varta AGM 80 Ah
battery exposed the stale HA source-heartbeat defect described above. The transaction
rejected before any edge command and did not alter the external HANDS_OFF program.
The corrected firmware source compiles in CI but is **not yet physically installed**.

The detailed evidence record is:

`docs/assistant/PHYSICAL_EDGE_VALIDATION_2026-09-02.md`

This closes the basic **edge** implementation gate for D056, D060 release and the
D061 ownership primitive. It also records a real read-only bot preflight failure. It
does **not** close the complete D061/D062 bot-level failure-injection gate; the
unchecked items above remain pending.

## Rollback

Keep the last known working Home Assistant YAML and secrets backup before any
flash.

If the new firmware is unsuitable:

1. ensure RD6018 Output OFF is safe and verified;
2. restore the previous YAML/package set;
3. Validate;
4. compile and flash the previous firmware;
5. verify the node reconnects and Output remains in the intended safe state.

Do not use rollback as a reason to bypass the new firmware's boot quarantine or
verified-OFF requirements.
