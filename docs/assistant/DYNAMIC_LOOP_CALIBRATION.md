# RD6018 Dynamic-Loop / Probe Characterization

Status: **OFFLINE CHARACTERIZATION TOOLING IMPLEMENTED; PHYSICAL CALIBRATION REMAINS Q005/Q014**

This workflow determines what the actual RD6018 + ESPHome + Home Assistant path can resolve before V2 chooses automatic controlled-probe parameters.

It deliberately does **not** decide a production current-step size, settle time, sample count, or meaningful-change threshold.

## Why this must be measured

The controlled `ΔI -> ΔV_BAT` experiment is a two-wire charge-response measurement. It contains battery electrochemical/polarization response plus leads, contacts and relevant RD6018 path effects. It is not battery DC internal resistance.

The current additive ESPHome telemetry package contains some explicit 5 s template intervals (for example temperature), but does not establish the complete real polling/update cadence of the existing `powersupply` Modbus controller. Therefore Q005/Q014 must use timestamps from actual observations rather than assuming a 5 s sample path.

## Bench trace phases

Capture one JSON object per actual observation with explicit operator phase labels:

```text
baseline
    -> current still at the ordinary charging setting

stepped
    -> current limit has been reduced; collect from immediately after the step through settling

restored        # optional but strongly recommended
    -> original configured current restored and verified
```

The characterization experiment must obey the existing safety principle: current may only be reduced from the ordinary target. Do not raise current or voltage solely to improve the test signal.

## JSONL sample schema

Required fields:

```json
{
  "timestamp_s": 1725000000.0,
  "phase": "baseline",
  "battery_voltage_v": 14.102,
  "current_a": 6.01
}
```

Recommended context when available:

```json
{
  "configured_current_a": 6.0,
  "output_voltage_v": 14.121,
  "temp_ext_c": 25.0,
  "regulation_mode": "cc"
}
```

Use the timestamps of the observations themselves. Do not synthesize evenly spaced timestamps from an assumed ESPHome interval.

## Analyze

```bash
python tools/characterize_dynamic_loop.py probe.jsonl
```

Optional:

```bash
python tools/characterize_dynamic_loop.py probe.jsonl \
  --baseline-phase baseline \
  --stepped-phase stepped \
  --tail-count 3 \
  --output report.json
```

## Reported descriptive quantities

For each phase:

- sample count and observed duration;
- actual median/min/max inter-sample cadence;
- Vbat median/mean/MAD/span;
- measured-current median/mean/MAD/span;
- configured-current statistics when supplied;
- Vout statistics when supplied;
- temperature statistics;
- observed regulation modes;
- smallest positive difference actually observed between unique values (`observed_min_step`).

`observed_min_step` is a descriptive property of that trace, **not** proof of ADC resolution. Noise/filtering/rounding may make it larger or smaller than the hardware quantization.

For baseline -> stepped:

- baseline and stepped median U/I;
- actual measured `ΔI` and `ΔV_BAT`;
- descriptive `dynamic_loop_mohm = ΔV/ΔI`;
- terminal/tail median;
- every stepped sample's voltage/current deviation from the tail median.

The tail-deviation series lets us inspect settling directly instead of inventing a universal settle timeout.

## V_OUT - V_BAT boundary

When both values are supplied the tool reports the raw difference only as:

```text
output_minus_battery_voltage
```

It also emits:

```text
output_minus_battery_voltage_is_descriptive_not_resistance
```

Do **not** reinterpret this as cable/contact/path resistance. The exact RD6018 internal red/green measurement topology has not been proven well enough for that inference.

## Data collection matrix before enabling automatic probes

Capture multiple repeats under the same unchanged physical connection (`connection_id`) and at least:

1. stable CC at ordinary Main current;
2. at least two safer current-reduction amplitudes chosen manually for characterization;
3. repeated runs without reconnecting clips;
4. reconnect clips/leads and repeat to quantify connection sensitivity;
5. several battery SOC regions where normal charging naturally provides CC;
6. at least two battery temperatures in the normal safe range, without intentionally heating/cooling the battery;
7. stable-load/dummy-load characterization where appropriate to separate charger-path repeatability from battery electrochemistry.

Record the exact RD model/serial/firmware and calibration fingerprint with each run when available. A hardware/firmware/calibration change invalidates direct comparison to old characterization baselines.

## How Q005 should eventually use this

Only after real reports exist should Q005 choose:

- allowed stages/modes;
- minimum actual current reduction (`|ΔI|`) above measured noise/quantization;
- settle window long enough for the selected evidence definition;
- sample count/interval compatible with actual cadence;
- readback tolerance;
- abort rules;
- minimum signal-to-noise criterion;
- connection identity lifecycle.

A chosen production parameter must point back to characterization evidence. Do not derive it solely from the current placeholder defaults in `ProbePlan`.

## How Q014 should eventually close

Q014 can close only when actual RD/HA traces establish whether:

- Vbat and current have enough repeatability for longitudinal dynamic-loop evidence;
- the observed signal is materially larger than noise/quantization;
- reconnection sensitivity is understood;
- sample cadence is sufficient;
- the metric adds useful information beyond ordinary charge U/I/T trajectories.

If those conditions fail, remove/disable dynamic-loop as health evidence rather than tuning around an unresolvable signal.
