# HydroSense presentation operation guide

## Single snapshot contract

The ESP32 samples the three ADC1 channels every second using trimmed samples and
`analogReadMilliVolts()`. The latest completed set is sent as one eight-field
ThingSpeak snapshot every 20 seconds. The backend polls at 20 seconds and the
website refreshes on the same cadence. The OLED is allowed to refresh sooner
(500 ms) from that latest completed local set so a critical local alert is not
delayed.

ThingSpeak field mapping is unchanged: 1 display pH, 2 turbidity estimate, 3
TDS estimate, 4 severity, 5 pH board V, 6 turbidity board V, 7 health bitmask,
8 direct TDS ADC V. A successful HTTP response with a positive entry id is the
only firmware success condition; a rejected or failed upload is shown as an
error and is not represented as cloud sync.

## Presentation profiles

The dashboard's demo-only selector persists one profile state together with the
reading record. It is deliberately unavailable in real mode: selecting a
profile must not overwrite incoming ESP32/ThingSpeak measurements.

| Profile | Measured pH ADC / board V | Turbidity board V | TDS ADC V | Display treatment |
| --- | --- | ---: | ---: | --- |
| Kent RO Water | 1.908 / 4.770 | 0.939 | 0.307 | Reference profile; pH is `DEMO_ESTIMATE` 7.00 |
| Household Tap Water | 1.908 / 4.770 | 1.484 | 2.155 | Reference profile; pH is `DEMO_ESTIMATE` 7.20 |
| Contaminated demonstration | physical voltage remains visible | physical voltage remains visible | physical voltage remains visible | adjustable `DEMO_ESTIMATE` pH only; salt and dirt never infer pH |

The reference pH estimates are presentation values, not laboratory results.
`ph_sensor_estimate` remains null while the interface response is suspect;
`ph_demo_estimate` and `ph_display_source=DEMO_ESTIMATE` make this explicit in
the API and dashboard.

## Models and limits

* pH: a stored NVS three-buffer calibration takes precedence. The old candidate
  transfer would convert 4.770 V to 13.36; because that voltage is unchanged
  between RO and tap, the firmware now reports `PH_RESPONSE_SUSPECT` and retains
  the voltage instead of showing that false value.
* Turbidity candidate: `-1120.4 V² + 5742.3 V - 4352.9`, bounded to 0–4.5 V
  and labelled model-based until standards validate the unmarked module. It
  produces approximately 51.2 and 1701.3 NTU-equivalent for the RO and tap
  reference voltages respectively. Those values are not safety claims.
* TDS: `0.5 × (133.42 Vc³ − 255.86 Vc² + 857.39 Vc) × K`, where
  `Vc=V/(1+0.02(T−25))`. At nominal 25°C and K=1 the references are about
  121.5 ppm and 997.4 ppm. A saved NVS K-factor overrides the default.

Project hazard thresholds are pH <5.0 or >9.5, TDS >700 ppm, and turbidity
>150 NTU. Missing/faulted inputs are never converted to zero. Valid calibrated
TDS and turbidity are evaluated separately, with hysteresis in the firmware;
salt therefore yields a TDS reason and dirt a turbidity reason when their
respective physical readings cross limits. The pH demo value is separately
labelled and cannot turn a pH sensor failure into a safe result.

## OLED and buzzer

Normal display uses the latest snapshot. An unverified saturated pH interface
shows `SUSPECT (x.xxV)` instead of a pH number. A threshold breach flashes the
specific cause (for example `HAZARD: TDS TURB`); an electrical/probe failure
shows its fault status and water quality is unknown rather than safe.

GPIO25 uses non-blocking patterns: warning is 150 ms on / 850 ms off, critical
is a double beep, and a 10-second maximum alarm is followed by a 30-second
cooldown. It stops after the relevant validated condition clears through the
configured hysteresis. Probe/electrical faults are visually distinct and do not
pretend to be confirmed contamination.

## Hardware follow-up

The constant 4.770–4.771 V pH-board observation is evidence to inspect the
interface board supply/output stage, divider wiring, shared ground and electrode
response in actual pH 4/7/9 buffers. Earlier 1.346 V and 1.489 V ADC readings,
and the listed dry/unknown-liquid readings, are retained as electrical history
only and are not calibration points.

ThingSpeak's current free-account write limit is 15 seconds, so the configured
20-second cadence is within it. This repository cannot confirm a live Channel
3570138 entry without the active credentials/device; check the ESP32 serial log
for a positive ThingSpeak entry id and then the backend's sync response before
claiming a cloud round-trip.
