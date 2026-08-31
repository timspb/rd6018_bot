# External Battery Temperature Sensor Integrity

Status: **ACCEPTED SAFETY DESIGN / PARTLY IMPLEMENTED / CONSECUTIVE-ANOMALY DETECTOR NOT YET IMPLEMENTED**

This note defines the safety contract for the external battery-temperature channel (`temp_ext`) during any managed charge, with particular importance in Recovery/Mix high-voltage stages.

The external battery temperature is safety authority. A managed charge must not continue merely because the last numeric value looked reasonable after the sensor path has failed, and it must not blindly trust a stream of fresh but physically implausible values.

## Existing production foundation

Production V2 already treats `temp_ext` as required runtime telemetry and as a freshness-critical channel. Missing/non-finite/unavailable temperature or stale/incoherent source metadata while charging is fail-closed and requests verified Output OFF.

The corrected RD6018 telemetry package publishes the external-temperature view on a nominal 5 s interval. A flat but freshly reported temperature is valid; unchanged value alone is not a fault.

This existing fail-close behavior must not be weakened by the consecutive-anomaly mechanism below.

## Three failure classes

### A. Missing / unavailable / stale source

Examples:
- entity becomes unavailable/unknown;
- numeric value disappears or becomes non-finite;
- source timestamp stops advancing beyond the accepted freshness window;
- source metadata is missing/incoherent so freshness cannot be proved.

Action:

```text
freshness proof lost
        -> fail closed
        -> verified Output OFF
        -> no N-sample grace
```

Do **not** count repeated HA polls of the same stale sample as multiple observations. Loss of freshness is a time/source-integrity fault, not an N-sample plausibility vote.

### B. Fresh sample is an immediate hard-safety condition

Existing thermal hard limits remain authoritative. For example, a real fresh battery temperature at/above the configured critical threshold is an immediate safety event; it does not wait for the anomaly counter.

Likewise, if physical bench characterization identifies an unambiguous RD6018 external-probe disconnect/error sentinel or impossible raw register encoding, that confirmed sentinel may be classified as immediate invalid telemetry. Do not guess sentinel values from unrelated sensor families.

Action:

```text
fresh + proven hard-invalid/hard-dangerous sample
        -> verified Output OFF immediately
```

### C. Fresh but suspicious / atypical samples

This is the new accepted mechanism.

A single fresh temperature sample may be corrupted or transiently abnormal without proving sensor failure. Fresh samples that violate a calibrated plausibility/continuity model are therefore tracked as a consecutive anomaly sequence.

Conceptually:

```text
fresh source sample
    |
    +-- normal/plausible --------> anomaly_count = 0
    |
    +-- suspicious/anomalous ----> anomaly_count += 1
                                      |
                                      +-- anomaly_count < N -> continue observing
                                      |
                                      +-- anomaly_count >= N
                                              -> verified Output OFF
                                              -> latch sensor-integrity fault
```

`N` counts **new source reports**, not bot polling iterations and not repeated reads of the same HA state/timestamp.

A fresh valid sample resets the consecutive anomaly counter. A stale sample never resets it and is handled by Class A instead.

## What may become an anomaly after calibration

The exact thresholds remain empirical. Candidate evidence includes:

- implausible absolute external-battery temperature while the value is still numerically finite;
- physically implausible step change between adjacent fresh reports;
- physically implausible temperature slope for the battery/probe thermal mass;
- oscillation/jitter pattern characteristic of a failing probe/connection;
- raw sign/magnitude combinations shown by bench testing to correspond to probe disconnect/fault while still decoding to a finite number.

Do not classify a constant temperature as anomalous merely because the numeric value is unchanged. Home Assistant `last_reported`/source heartbeat is the liveness authority for that case.

Do not invent generic DS18B20-style sentinel values for the RD6018 probe path. The actual RD6018 sign/magnitude registers and failure behavior must be characterized on the installed hardware.

## Relationship to ordinary thermal control

Sensor integrity and thermal thresholds are different safety mechanisms:

```text
thermal policy:
  real T rises -> warning / Cooling / critical OFF

sensor-integrity policy:
  cannot trust T -> OFF
```

An integrity fault must never be converted to "assume a safe temperature" or "continue until 40/45 C". If the temperature channel cannot be trusted, automatic charging authority ends.

## Relationship to communication-loss watchdog

The external-temperature integrity guard is independent from the 15-minute communication-loss dead-man design.

- telemetry/source integrity failure should shut down on its own shorter observation/freshness timescale;
- the 15-minute edge/native dead-man remains a backstop for wider bot/HA/ESPHome/control-path failures;
- neither mechanism extends the Mix chemistry clock or the Mix automatic-authority maximum.

## Initial N policy

The architecture accepts `N` consecutive anomalous **fresh** source reports, but does not yet freeze a universal production value.

The corrected external-temperature entity currently publishes nominally every 5 s, so a candidate such as `N=3` would represent roughly 10–15 s of persistent anomalous evidence depending on report timing. That is a calibration starting point, not an accepted constant.

The final `N`, step/slope limits and any hard sentinel classification must be chosen from physical bench traces of:

- stable attached probe;
- deliberate probe disconnect/reconnect;
- contact/intermittency disturbance;
- sensor/cable movement;
- real heating/cooling transitions;
- HA/source timestamp behavior during unchanged values and communication interruption.

Higher-energy stages may use an equal or stricter integrity policy; they must never use a looser one.

## Fault lifecycle

Once the consecutive anomaly threshold or a hard integrity fault has caused shutdown:

1. request Output OFF;
2. require physical OFF confirmation;
3. latch/report the sensor-integrity fault for the active program;
4. do not automatically resume the previous energized stage merely because the next temperature sample looks normal;
5. require fresh valid sensor evidence and the normal operator/session re-authorization/restart path before any new Output ON.

This prevents a loose connector from alternating `bad -> OFF -> good -> automatic ON -> bad` indefinitely.

## Required implementation tests

Software regressions must prove at least:

- one suspicious fresh sample does not trip when `N > 1`;
- `N` distinct anomalous source reports cause verified OFF;
- one fresh valid report resets the consecutive anomaly counter;
- repeated polls of one cached anomalous sample count once, not N times;
- stable unchanged valid temperature with fresh `last_reported` remains valid;
- stale/missing/unavailable `temp_ext` still fails closed without waiting for N;
- critical real temperature remains immediate according to thermal policy;
- OFF-unconfirmed containment remains active if the shutdown command cannot be physically proved;
- restart does not silently re-energize a program stopped for sensor-integrity failure.

## Physical validation gate

Before this detector becomes production authority, reproduce the installed RD6018 external-probe failure modes on the actual hardware and capture raw registers 34/35 plus the published V2 temperature/source timestamps. Use those traces to select the anomaly classes, `N`, step/slope thresholds and any confirmed disconnect sentinel.
