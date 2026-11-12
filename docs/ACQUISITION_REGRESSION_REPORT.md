# Acquisition regression repair

## Finding

The calibration refactor did not alter GPIO assignments, ADC resolution, ADC
attenuation, divider values, or NVS in a way that could transform a live input
voltage. It did, however, add a cross-cycle "stuck" detector to all three
analog paths. With one acquisition per second, a value that changed by less
than 0.5 mV for more than 15 cycles was reported as `STATUS_STUCK` and removed
from processing/upload.

That is incompatible with the recorded standalone stability: pH varied by only
4 mV, turbidity by 5–6 mV, and RO TDS by 13 mV. It is especially unsafe with
integer-millivolt ESP32 readings, where a valid stable signal can repeat
exactly. This was a software false-fault classification, not evidence of a
disconnected sensor.

## Repair

* Acquisition now uses 32 samples per reading, matching the standalone sketch.
* Raw ADC count and `analogReadMilliVolts()` are retained independently; board
  reconstruction is `V_adc × 2.5` only for pH/turbidity. TDS remains `×1.0`.
* Calibration code consumes the acquired voltage and never writes it back.
  NVS is read only for conversion coefficients and retains precedence for valid
  saved calibration.
* Cross-cycle stuck detection is disabled by default. It remains an explicit,
  testable opt-in control for a hardware-validated deployment.

## What did not change

`analogReadResolution(12)` and `ADC_11db` remain the integrated settings.
GPIO34, GPIO32, GPIO35, I2C GPIO21/22 and buzzer GPIO25 do not conflict.
The one-second acquisition overwrites each `SensorReading`; no acquisition
path returns a cached earlier reading. OLED/cloud consume the same latest
completed snapshot.

## Conversion results

The pH E-201-C is an electrode; its interface board is unconfirmed. The two
current reference samples both yield 1.908 V ADC / about 4.770 V board, so
there is no evidence for a valid sample-discriminating physical pH transfer.
The firmware preserves that voltage, labels an unverified pH response as
suspect, and reserves `DEMO_ESTIMATE` for separately labelled presentation
values. A pH 4.01/7.00/9.18 buffer calibration remains authoritative.

The candidate SEN0189 quadratic yields about 51.2 and 1701.3 JTU-equivalent
at 0.939 V and 1.484 V. The vendor equation is a JTU model, not a verified NTU
calibration for this unknown module, so the application labels it provisional.

At 25°C and K=1, the existing TDS cubic yields about 121.5 ppm at 0.307 V and
997.4 ppm at 2.155 V. A valid saved NVS K-factor supersedes 1.0.
