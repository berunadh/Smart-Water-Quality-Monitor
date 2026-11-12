# Hardware-Specific Research & Calibration Report

**Report date:** 2026-11-11  
**Scope:** HydroSense ESP32 firmware, telemetry pipeline, API, and dashboard.  
**Evidence boundary:** This repository contains source and written wiring documentation but no PCB photograph, PCB silkscreen photo, purchase record, or laboratory reference-solution readings. Historical voltage observations are treated as observations, never as certified calibration points.

## 1. Model identification and confidence

| Item | Identification | Confidence | Evidence and decision |
|---|---|---:|---|
| pH electrode | **E201-C composite glass electrode** | Confirmed | Explicitly supplied model. The available E-201-C instruction sheet specifies pH 0–14, 0–80 °C, zero point pH 7 ± 0.5, response under 2 minutes, internal resistance under 250 MΩ, repeatability under 0.017 pH and noise under 0.5 mV. |
| pH interface PCB | **Unidentified 6-terminal pH conditioning board** | Unconfirmed | Labels `T, D, P, G, G, U+` match the common PH-4502C-style header order but are not a unique model number. No board image/marking establishes PH-4502C. Firmware uses its documented 0–5 V / pH 0–14 transfer only as a labelled model-based estimate. |
| Turbidity probe + interface | **Unidentified analog optical transmission module** | Unconfirmed | A 5 V, analog optical transmission probe is compatible with DFRobot SEN0189, but neither a SEN0189 marking nor its distinctive confirmed board/pinout is present in evidence. Firmware uses its published quadratic only as a labelled model-based estimate. |
| TDS board | **`TDS Meter V1.0` analog board; possible SEN0244-compatible clone** | Possible match only | DFRobot SEN0244 documentation and its public V1.0 schematic describe the same general board type and cubic model, but `TDS Meter V1.0` alone does not prove manufacturer or transfer curve. The existing recorded TDS calibration is preserved and the polynomial remains explicitly model-based unless NVS holds a physical-standard calibration. |

### Sources and what they establish

- [E-201-C composite electrode instruction sheet](https://makerhero.com/img/files/download/E-201-pH-Electrode-Datasheet.pdf) establishes the supplied electrode's stated range, zero point, response time, and repeatability; its manufacturer identity is not established by the hosted copy.
- [PH-4502C-style ESP32 wiring reference](https://boardpilot.agentflowbind.com/parts/ph-4502c/) records the matching `T, D, P, G, G, U+` header order, 5 V supply, and approximately 2.5 V pH-7 offset; the source is a candidate-equivalent reference, not identification of this PCB.
- [DFRobot SEN0189 official wiki](https://wiki.dfrobot.com/sen0189) specifies the **confirmed SEN0189 only** as 5 V, 0–4.5 V analog/digital, 40 mA maximum, and less than 500 ms response. It is a candidate reference, not evidence that this project has an SEN0189.
- [DFRobot SEN0189 formula discussion](https://www.dfrobot.com/forum/topic/320476) records DFRobot's published `JTU = -1120.4V² + 5742.3V - 4352.9` curve. It is intentionally not enabled without model confirmation and actual standards.
- [DFRobot SEN0244 official calibration guide](https://wiki.dfrobot.com/sen0244/docs/20304) recommends a known standard (its current guide gives 707 ppm / 1413 µS/cm at 25 °C), stable immersion, and calibration save/verification. This project continues to accept any certified 10–3000 ppm reference, including an existing 342 ppm procedure.
- [DFRobot SEN0244 V1.0 schematic](https://dfimg.dfrobot.com/nobody/wiki/2adb0fdcbe3307f72f8850b188aafdaf.pdf) is useful only as a possible-match reference for the TDS board; it does not authenticate the project's board.

## 2. Electrical measurement contract

The physical wiring is retained:

| Sensor | GPIO / ADC | Supply | Divider | Conversion domain |
|---|---|---|---|---|
| E201-C pH board `P` | GPIO34, ADC1_CH6 | 5 V board | 15 kΩ high side / 10 kΩ to GND | `V_board = 2.5 × V_ADC` |
| Optical turbidity board `OUT` | GPIO32, ADC1_CH4 | 5 V board | 15 kΩ high side / 10 kΩ to GND | `V_board = 2.5 × V_ADC` |
| TDS Meter V1.0 `A` | GPIO35, ADC1_CH7 | 3.3 V | none | `V_board = V_ADC` |

The ESP32 remains at 12-bit / `ADC_11db`; the firmware uses `analogReadMilliVolts()` plus raw-count checks and treats direct ADC readings at or above 3.05 V (or raw count 4000) as an electrical hazard. ADC1 remains necessary because Wi-Fi uses ADC2.

## 3. Chosen equations and calibration provenance

### pH — `MODEL_BASED_PROVISIONAL` until measured buffers are committed

The E201-C is a passive electrochemical electrode. Its ideal Nernst slope is:

`S(T) = 2.303 × R × (T + 273.15) / F V/pH`

At 25 °C, the magnitude is about 59.16 mV/pH at the **electrode**. The interface-board gain and offset transform this into a board-output voltage, so electrode theory cannot supply this project's board-voltage-to-pH equation.

The implemented model is measured three-point, piecewise linear interpolation in reconstructed board mV:

`s_acid = (7.00 - 4.01) / (V7 - V4)`  
`s_base = (9.18 - 7.00) / (V9 - V7)`

`pH = 7 + s_acid × (V - V7)` on the acid branch, otherwise `7 + s_base × (V - V7)`.

For an immediate, honest display, firmware applies the closest documented generic-board transfer: `pH_est = 2.8 × V_board`. It is represented internally by derived model points pH 4.01 → 1.432 V, pH 7.00 → 2.500 V, and pH 9.18 → 3.279 V; these are mathematical points from the assumed 0–5 V / pH 0–14 mapping, **not measurements from this board or buffers**. The model is permitted across 0–5 V and carries `MODEL_BASED_PROVISIONAL`. Existing valid NVS values always take precedence and remain untouched.

Coefficient record before physical calibration:

| Field | Value |
|---|---|
| Source | Candidate PH-4502C-style 5 V board documentation: pH 7 at 2.5 V and 0–5 V mapped to pH 0–14; E201-C sheet supports electrode behaviour |
| Board model / supply | Unidentified / documented 5 V |
| ADC / divider | ESP32 ADC1 11 dB / 2.5× reconstruction |
| Reference points | No actual points used. Required for verification: actual pH 4.01, 7.00, 9.18 buffers |
| Status | `MODEL_BASED_PROVISIONAL`; `VERIFIED_CALIBRATION` only after NVS buffer capture |
| Valid range | Estimated 0–5 V board transfer; verified calibration constrains to captured range |
| Expected accuracy | Unknown and potentially large offset/slope error until buffer verification |

### Turbidity — `MODEL_BASED_PROVISIONAL` until certified standards are committed

The presentation model is the published SEN0189 5 V polynomial: `JTU_est = -1120.4V_board² + 5742.3V_board - 4352.9`, clamped to 0–3000. The dashboard uses the existing NTU field but labels it **JTU/NTU-equivalent MODEL PROVISIONAL**. JTU and NTU are not silently asserted to be identical, and the model is not an identification of the installed board. Optical response varies with geometry, particle type, colour, supply, and board gain.

The implemented model is the project probe's two-point measured transmission curve:

`NTU = NTU_clear + ((V_clear - V) / (V_clear - V_standard)) × (NTU_standard - NTU_clear)`.

The published curve is used for 0–4.5 V reconstructed board output. The older fabricated linear reference points are not used. Existing valid NVS two-standard records always supersede this model and retain the actual project probe's linear calibration.

Coefficient record before physical calibration:

| Field | Value |
|---|---|
| Source | DFRobot-published SEN0189 quadratic, used only as closest documented module approximation |
| Module / supply | Unidentified analog optical module / documented 5 V |
| ADC / divider | ESP32 ADC1 11 dB / 2.5× reconstruction |
| Reference points | None used. Required: certified low/clear and higher standards, with actual values recorded |
| Status | `MODEL_BASED_PROVISIONAL`; `VERIFIED_CALIBRATION` only after NVS standards |
| Valid range | 0–4.5 V model input; verified calibration constrains to captured standard interval |
| Expected accuracy | Unknown; JTU/NTU equivalence is not guaranteed; check an independent turbidimeter or standards |

### TDS — preserve the working path and NVS calibration record

The existing direct-ADC model is unchanged:

`V_comp = V_ADC / (1 + 0.02 × (T - 25))`  
`TDS_raw = 0.5 × (133.42V_comp³ - 255.86V_comp² + 857.39V_comp)`  
`TDS = k × TDS_raw`.

At the installed system's nominal 25 °C, `V_comp = V_ADC`. A real TDS reference produces and stores `k = reference_ppm / TDS_raw` in NVS only after live readback is within ±5%. The module identity is unconfirmed, so the uncorrected cubic has `MODEL_BASED_PROVISIONAL` status; an existing valid NVS `k` is `VERIFIED_CALIBRATION` for its reference point, not a full-range certification. The code does not reset, replace, or erase any TDS key.

| Field | Value |
|---|---|
| Source | Existing project implementation; possible DFRobot SEN0244-compatible cubic |
| Board / supply | `TDS Meter V1.0` (unconfirmed manufacturer) / 3.3 V |
| ADC / divider | ESP32 ADC1 11 dB / direct, multiplier 1.0 |
| Physical references | Existing valid NVS record retained; otherwise certified standard still required |
| Status | `VERIFIED_CALIBRATION` only with valid NVS reference; otherwise `MODEL_BASED_PROVISIONAL` |
| Operating range | Firmware input safety under 3.05 V; calibration proposal 0.10–2.95 V and 10–3000 ppm; physical plausibility cap 5000 ppm |
| Limitation | No installed temperature sensor; use near 25 °C or treat temperature error explicitly |

## 4. Historical observation analysis

| Channel | Observations | Engineering interpretation |
|---|---|---|
| pH | 1.346 V ADC → 3.365 V board; 1.908 V ADC → 4.770 V board; raw 2192; standalone variation 4 mV | Both ADC voltages are safely below 3.05 V. The 4 mV variation indicates good short-term electrical repeatability, not accuracy. The candidate model makes 4.770 V → **pH 13.356 MODEL_BASED_PROVISIONAL**; it is visible but cannot alert, sound the buzzer, or create WQS hazard status. Raw 2192 does not reconstruct to 1.346 V through a naïve `raw/4095 × 3.3` calculation, so raw counts and calibrated mV must not be mixed across firmware/attenuation observations. No pH buffer identity accompanies either voltage. |
| Turbidity | 0.171 V → 0.428 V; 0.334 V → 0.834 V; 0.095 V → 0.238 V; 0.594 V → 1.484 V; raw 561; standalone variation 5 mV | All shown ADC measurements are below 3.05 V and above the 0.08 V disconnect rule. The 5 mV variation is short-term stable. The SEN0189 candidate model makes 1.484 V → **1701.27 JTU/NTU-equivalent MODEL_BASED_PROVISIONAL**; it is visible but non-actionable until standards verify it. Their broad range could arise from real optical change, a different supply/output range, wiring/contact variation, or a non-SEN0189 module. |
| TDS | dry 0.142 V; unknown liquid 1.782 V; latest direct ADC 2.155 V; raw 2498; prior integrated 1054–1076 ppm | 0.142 V is consistent with the ESP32 11 dB low-end intercept/dry baseline behaviour and must not be converted to 0 ppm. Both wet values are electrically safe. The unscaled model gives about 735 ppm at 1.782 V and 997 ppm at 2.155 V; the latter is directionally consistent with the prior ~1054–1076 ppm report, but the liquid was unknown so it is not a calibration validation. Raw 2498 versus 2.155 V again demonstrates why calibrated millivolts, rather than nominal raw scaling, are authoritative. |

### Why the earlier pH and turbidity readings said `OUT OF RANGE`

Those were **calibration-window rejections, not electrical over-range failures**. The old pH RAM curve allowed only 2.108–3.040 V reconstructed board output; both observed 3.365 V and 4.770 V were outside it. The old turbidity RAM curve allowed only 3.500–4.000 V; every observed output (0.238–1.484 V) was outside it. The replacement uses documented model estimates over their defined board-voltage ranges and visibly marks them `MODEL_BASED_PROVISIONAL`; it does not claim those values are verified.

## 5. Integration and confidence display

The complete path remains:

`physical sensor → ADC1 acquisition → divider reconstruction → model/calibration → validator/WQS → ThingSpeak → FastAPI → React dashboard`.

- GPIO assignments, dividers, OLED, buzzer, ThingSpeak mapping, and NVS namespace `watersens` are preserved.
- pH and turbidity model estimates flow through the existing Fields 1 and 2, with health bits 12 and 13. Diagnostic voltages still upload. They remain non-actionable for WQS, critical hazard, and buzzer decisions until actual calibration.
- FastAPI now derives and returns a per-sensor `*_calibration_status`: `VERIFIED_CALIBRATION`, `MODEL_BASED_PROVISIONAL`, `DEMONSTRATION_ESTIMATE`, `UNCALIBRATED`, or `SENSOR_FAULT`.
- The dashboard shows this exact confidence label under each pH/NTU/ppm card. A model-based value is no longer visually indistinguishable from a verified physical calibration.

## 6. Physical calibration and verification still required

1. Photograph both unconfirmed PCBs front/back and record every silk-screen label, IC marking, connector order, supplier listing, and supply voltage measured at the board. This is required before assigning PH-4502C or SEN0189 equations.
2. For E201-C: condition/rinse the electrode as directed by its instruction sheet; capture stable reconstructed board voltages in certified pH 7.00, 4.01, and 9.18 buffers near the same temperature. Use `ph cal 7.00`, `ph cal 4.01`, `ph cal 9.18`, then `ph confirm`; verify all three buffers after reboot.
3. For turbidity: use a clean vessel and certified standards that bracket intended use; record standard values, batch/expiry, board supply, board-output voltage, sample temperature, probe depth, and settling time. Capture `turb cal clear <actual-NTU>` and `turb cal <actual-NTU>`, then `turb confirm`; independently check an intermediate standard.
4. For TDS: do **not** reset it. First inspect `cal status`. If no NVS record exists, use a certified known-TDS solution near 25 °C, stage `tds cal <ppm>`, and commit only after `tds confirm` passes. Retain the solution's ppm/EC basis and temperature in the calibration log.
5. Upload only live readings after each confirmation. Verify Field 5/6 show board voltages, Field 8 (8-field profile) shows direct TDS ADC voltage, Field 7 carries health/confidence flags, and the dashboard labels each sensor correctly.

## 7. Modified files and verification

- `firmware/water_monitor/config.h`: installs documented, clearly provisional pH and turbidity model coefficients while retaining existing NVS and TDS configuration.
- `backend/app/schemas/sensor.py`: exposes the five explicit calibration-confidence states in API responses.
- `backend/app/services/mode_service.py`: removes misleading hard-coded provisional voltage ranges from user-facing messages.
- `frontend/src/types/index.ts` and `frontend/src/components/SensorCard.tsx`: render the returned confidence state.
- `backend/tests/test_calibration_confidence.py`: tests verified, provisional, demo, uncalibrated, and fault provenance paths.

Run from the project root:

```bash
cd backend && ./venv/bin/python -m pytest -q
cd ../frontend && npm run build
./scripts/compile_firmware.sh
```

The firmware compile command requires the local Arduino CLI/ESP32 core and project libraries; no physical sensor upload or calibration was performed by this software change.
