# Sensor Calibration Protocol & Live Bench Procedures

> [!IMPORTANT]
> **Strict Scientific Rule**: Generic polynomial formulas (such as unverified quadratic formulas found on online hobby blogs) produce erratic, negative, or meaningless values due to batch differences in optical components, op-amp drift, and resistor tolerances.
> 
> Until physical calibration is performed with standard buffer solutions, the system displays **`CALIBRATION PENDING`** on the OLED and reports voltages honestly.

---

## 1. pH Sensor Calibration (E201-C BNC Electrode)

### Materials Required:
1. Standard pH Buffer Powder or Ready-to-Use Solutions:
   - **pH 7.00 Buffer** (Neutral reference)
   - **pH 4.01 Buffer** (Acidic reference)
   - *Optional*: **pH 10.01 Buffer** (Alkaline reference for 3-point calibration)
2. Distilled or deionized water for rinsing the probe between immersions.
3. Clean, lint-free wipe.

### Step-by-Step Two-Point Calibration Procedure:

1. **Physical Preparation**:
   - Power on the ESP32 and open the **Serial Monitor** at **115200 baud**.
   - Type `status` to verify analog acquisition is operational.
   - Unscrew the protective storage cap from the E201-C glass bulb electrode (be careful not to lose the storage solution inside the cap).
   - Rinse the glass bulb gently with distilled water and blot dry with a lint-free tissue (do not rub the bulb).

2. **Step A: Neutral Buffer (pH 7.00)**:
   - Submerge the glass bulb into the **pH 7.00 buffer solution**.
   - Stir gently for 10 seconds and let the reading settle for 60 seconds until the voltage stabilizes.
   - Note the reconstructed voltage printed on the Serial Monitor (`Vboard`).
   - *(Optional Board Hardware Trimming)*: If your green board has an offset potentiometer, turn the potentiometer until `Vboard` reads approximately **2.50 V** (which corresponds to ~1.00 V at the ADC).
   - In the Serial Monitor, send the command:
     ```text
     ph cal 7.00
     ```
   - The firmware records this voltage as the neutral zero-potential staging point.

3. **Step B: Acidic Buffer (pH 4.01) & Confirm**:
   - Remove the probe, rinse thoroughly with distilled water, and blot dry.
   - Submerge the probe into the **pH 4.01 buffer solution**.
   - Wait 60 seconds for thermal and chemical equilibrium.
   - In the Serial Monitor, send:
     ```text
     ph cal 4.01
     ```
   - Review the proposal and send `ph confirm` to commit the electrode slope ($mV/\text{pH}$) to NVS and activate live calibrated pH readings.

4. **Verification**:
   - Rinse and re-submerge into the pH 7.00 buffer. The OLED should now display:
     `pH: 7.00`
   - Rinse and submerge into tap water. You should observe a reading typically between 6.8 and 7.8.

---

## 2. Turbidity Sensor Calibration (Optical Probe)

The optical turbidity probe features an Infrared (IR) emitter LED and a phototransistor.

```
       [ IR Emitter ] ─── Light Beam ───► [ Phototransistor ]
                             │
                      Suspended Particles
                      (Scattering / Absorption)
```

- **Clear water (0 NTU)** allows maximum light through $\rightarrow$ Highest output voltage (~4.0V–4.5V reconstructed; ~1.6V–1.8V ADC).
- **Turbid water (high NTU)** scatters and blocks light $\rightarrow$ Output voltage drops.

### Calibration Procedure:

1. **Step A: Clear Water Zero Baseline (0 NTU)**:
   - Fill a clean, clear glass beaker with clean distilled or deionized water.
   - Clean the optical probe window with a microfiber cloth to ensure no fingerprints or air bubbles cling to the optical surface.
   - Submerge the probe completely up to the marked immersion line (keep the signal board dry!).
   - Ensure the probe is positioned in the center of the beaker, at least 2 cm away from the bottom and walls to prevent glass reflections.
   - Observe the reconstructed board voltage (`Vboard`). It should typically stabilize between **4.0 V and 4.5 V**.
   - In the Serial Monitor, send the command:
     ```text
     turb cal clear
     ```
   - The firmware stages this voltage as the `0 NTU` reference baseline.

2. **Step B: Standard Calibration & Confirm**:
   - Using a certified turbidity standard (e.g., 100 NTU Formazin standard):
   - Immerse the probe in the 100 NTU standard.
   - Send:
     ```text
     turb cal 100
     ```
   - Review the optical attenuation proposal and send `turb confirm` to commit to NVS.

---

## 3. TDS Sensor Calibration & Verification (`TDS Meter V1.0` on GPIO 35)

### Hardware Wiring & Electrical Contract
- **TDS `A` (Analog Out)** → **ESP32 GPIO 35** (`ADC1_CH7`, input-only)
- **TDS `+` (Power)** → **ESP32 3V3**
- **TDS `-` (Ground)** → **Common GND**
- **Voltage Divider**: **None** (`TDS_VOLTAGE_MULTIPLIER = 1.00f`; direct ADC input without the pH/turbidity ÷2.5 divider). TDS voltage is sampled using ESP32 factory-calibrated `analogReadMilliVolts()` alongside raw ADC counts.

### Important Limitations & Compatibility Notice
1. **Generic `TDS Meter V1.0` Compatibility**: The PCB silkscreen `TDS Meter V1.0` alone does **not** prove the module shares the exact DFRobot SEN0244 transfer curve (`TDS_raw = (133.42·V³ - 255.86·V² + 857.39·V) × 0.5`). Single-point `kFactor` calibration scales at `342 ppm`, but does **not** guarantee full-range `0–3000 ppm` linearity across every third-party board revision.
2. **Temperature Limitation (~25°C Nominal)**: The firmware has **no temperature sensor** and performs **no automatic temperature compensation**. Calibrate and measure near **25°C**; results are preliminary monitoring values, not laboratory-grade measurements.
3. **Preflight vs. Actual Calibration**:
   - **Preflight testing** (dry air and clean distilled/deionized water) only verifies wiring safety (`< 3.05 V`), signal stability, and baseline behavior—**never calibrate against tap water or an unknown preflight liquid**.
   - **Actual calibration** requires a **certified 342 ppm NaCl** TDS calibration solution (entered in **ppm**, **not** µS/cm) near **25°C**.
4. **Dry vs. Ultra-Pure Water Overlap**: If your board outputs a small baseline offset when dry (or falls inside the ESP32 `ADC_11db` 0–2 raw count deadzone), voltage alone cannot always distinguish dry air from near-0 ppm distilled water. An optional `tds dry` baseline command is provided only after verifying dry vs. distilled voltages on the final firmware.

### Step-by-Step TDS Calibration Procedure
1. **Preflight & Existing Calibration Check**:
   - Open Serial Monitor at **115200 baud** with **Newline** line ending.
   - Run `cal status` to verify existing **pH** (`GPIO34`) and **Turbidity** (`GPIO32`) calibrations are intact in NVS (`watersens` namespace). **Do not run `ph reset`, `turb reset`, or `cal reset`.**
   - Run `status` with the TDS probe dry in air, and again in clean distilled/deionized water after 30–60 s stabilization. Verify `Vadc < 3.05 V` and readings are stable.
2. **Prepare the Certified 342 ppm NaCl Solution (~25°C)**:
   - Pour a small amount into a clean cup, rinse the probe tip with distilled water, gently shake/blot excess drops, and immerse to the immersion mark (keep PCB/upper cable dry and probe centered away from walls/bottom; tap away bubbles). Wait **30–60 seconds**.
3. **Stage Calibration Proposal**:
   - Run:
     ```text
     tds cal 342
     ```
   - Verify the proposal reports `Sample Stability Check : PASSED (σ <= 0.050 V)`, `Electrical Voltage Check : PASSED (0.10 - 2.95 V)`, and `Derived Cell Constant (kFactor)` within `0.15 - 5.00`.
4. **Transactional Live Verification & NVS Commit**:
   - Keep the probe steady in the 342 ppm solution and run:
     ```text
     tds confirm
     ```
   - The firmware applies the candidate `kFactor` in RAM, performs a fresh live reading, checks that it falls within **±5.0% (`324.9–359.1 ppm`)**, and **only then** commits (`tds_cal`, `tds_k`, `tds_vs`, `tds_ref`) to NVS and verifies NVS readback. If live verification fails, nothing is written to NVS and any previous calibration is preserved.
5. **Post-Reboot Persistence Check**:
   - Unplug ESP32 USB power for 5 seconds, reconnect, open Serial Monitor at 115200 baud, verify `[CAL] Loaded TDS calibration from NVS` prints at boot, and run `cal status` to confirm TDS reports `CALIBRATED` alongside unchanged pH and Turbidity calibrations.

---

## 4. Interactive Serial CLI Command Reference

The ESP32 firmware includes a real-time calibration interpreter over USB Serial (**115200 baud, Newline**):

| Command | Action | Description |
| :--- | :--- | :--- |
| `help` or `?` | Help Menu | Displays all bench calibration, mode, and diagnostic commands |
| `status` | Print Diagnostics | Dumps raw ADC, $V_{ADC}$, $V_{board}$, health bitmask, and Wi-Fi state |
| `cal status` | Calibration Status | Shows NVS-stored pH, Turbidity, and TDS coefficients and live status |
| `ph cal 7.00` / `ph cal 4.01` / `ph confirm` | Calibrate pH | Two-point buffer calibration on GPIO34 (`÷2.5` divider); `ph cancel` / `ph reset` |
| `turb cal clear` / `turb cal <NTU>` / `turb confirm` | Calibrate Turbidity | Two-point optical calibration on GPIO32 (`÷2.5` divider); `turb cancel` / `turb reset` |
| `tds dry` / `tds dry clear` | Optional TDS Dry Baseline | Records or clears measured dry-air baseline voltage for GPIO35 |
| `tds cal 342` | Stage TDS Proposal | Computes `kFactor` in certified 342 ppm NaCl standard at ~25°C (ppm, NOT µS/cm) |
| `tds confirm` | Verify & Save TDS | Live-verifies reading (`325–359 ppm`) before committing TDS NVS keys |
| `tds cancel` / `tds reset` | Abort / Reset TDS | Cancels pending TDS proposal or clears ONLY TDS NVS keys |
| `mode drinking` / `mode regular` | Switch Mode | Switches between Drinking (IS 10500:2012) and Regular Usage limits |
| `cal reset` | Global Reset | **Caution**: Clears ALL sensor calibrations (pH, Turbidity, and TDS) |
