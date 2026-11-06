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
     cal_ph7
     ```
   - The firmware records this voltage as the neutral zero-potential point.

3. **Step B: Acidic Buffer (pH 4.01)**:
   - Remove the probe, rinse thoroughly with distilled water, and blot dry.
   - Submerge the probe into the **pH 4.01 buffer solution**.
   - Wait 60 seconds for thermal and chemical equilibrium.
   - In the Serial Monitor, send the command:
     ```text
     cal_ph4
     ```
   - The firmware calculates the exact electrode slope ($mV/\text{pH}$) and activates live calibrated pH readings.

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
     cal_turb_clear
     ```
   - The firmware locks this voltage as the `0 NTU` reference baseline.

2. **Step B: Standard Verification (Optional / Advanced)**:
   - If using a certified turbidity standard (e.g., 100 NTU Formazin standard):
   - Immerse the probe in the 100 NTU standard.
   - Send:
     ```text
     cal_turb_std 100
     ```

---

## 3. Interactive Serial CLI Command Reference

The ESP32 firmware includes a real-time calibration interpreter over USB Serial:

| Command | Action | Description |
| :--- | :--- | :--- |
| `help` or `?` | Help Menu | Displays the list of all available bench commands |
| `status` | Print Diagnostics | Dumps raw ADC, $V_{ADC}$, $V_{board}$, health bitmask, and Wi-Fi state |
| `cal_ph7` | Calibrate pH 7 | Samples current $V_{board}$ and registers it as pH 7.00 reference |
| `cal_ph4` | Calibrate pH 4 | Samples current $V_{board}$ and registers it as pH 4.01 reference |
| `cal_turb_clear` | Calibrate 0 NTU | Registers current $V_{board}$ as clean water baseline |
| `cal_reset` | Reset Calibration | Clears all coefficients back to `CALIBRATION PENDING` |
