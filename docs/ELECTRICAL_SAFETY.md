# Electrical Safety, ADC Limits & Hardware Commissioning Guide

> [!CAUTION]
> **MANDATORY SAFETY REVIEW**: Do not assume the sensor circuit is safe merely because previous code produced readings on a computer. An improperly wired analog signal can permanently destroy the ESP32 input gate oxide or cause latch-up.

---

## 1. Deep Analysis of Previous Software Output

Previous recorded software readings:
```text
pH ADC voltage:               3.134 V
Estimated pH board output:    7.835 V
Turbidity ADC voltage:        1.520 V
Estimated turbidity board output: 3.800 V
```

### Critical Electrical Observations:
1. **The Math Verification**:
   $$\text{Estimated Board Output} = \frac{V_{ADC}}{\text{Divider Ratio}} = \frac{3.134\text{ V}}{0.400} = 7.835\text{ V}$$
   $$\text{Turbidity Board Output} = \frac{1.520\text{ V}}{0.400} = 3.800\text{ V}$$

2. **The Turbidity Reading is Normal**:
   - The turbidity optical board is powered from 5V.
   - In clear or semi-clear water, optical sensor boards typically output between 3.5V and 4.2V.
   - Stepped down by the $0.400$ divider: $3.800\text{ V} \times 0.400 = 1.520\text{ V}$.
   - $1.520\text{ V}$ is comfortably inside the ESP32 11dB attenuation linear window ($150\text{ mV} - 2450\text{ mV}$).

3. **The pH Reading is DANGEROUSLY ABNORMAL**:
   - **Why 3.134V is alarming**: The ESP32 operates at a $3.3\text{V}$ rail. The maximum voltage measurable by the ESP32 ADC under 11dB attenuation is approximately $3.10\text{V} - 3.20\text{V}$. A reading of $3.134\text{V}$ is virtually in ADC saturation (near raw value 4095).
   - **The 7.835V Paradox**: If the green pH signal conditioning board is powered by the 5V USB rail, **it is physically impossible for a standard rail-to-rail operational amplifier to output 7.835V**.
   - **Root Cause Hypotheses for the 7.835V reading**:
     - **Hypothesis A (Open Ground / Disconnected Divider)**: The bottom $10\text{ k}\Omega$ resistor ground pin was loose or disconnected on the breadboard. Without a ground path, no current flows through the divider, turning the $15\text{ k}\Omega$ resistor into a simple series pull-up that passed the sensor's un-attenuated voltage (~3.1V–3.3V) directly onto GPIO 34!
     - **Hypothesis B (Swapped Resistors)**: If the $15\text{ k}\Omega$ and $10\text{ k}\Omega$ resistors were accidentally swapped ($R_1 = 10\text{ k}\Omega$, $R_2 = 15\text{ k}\Omega$), the ratio would be $15 / 25 = 0.600$, meaning a 5.0V output would produce $3.00\text{V}$.
     - **Hypothesis C (Over-voltage Power Supply)**: The green pH board was powered from a 9V battery or a 12V DC wall adapter instead of the regulated 5V USB rail.
     - **Hypothesis D (Floating ADC Pin)**: GPIO 34 was not physically connected to the probe during the test; high-impedance CMOS inputs float and pick up electromagnetic noise near the 3.3V rail.
     - **Hypothesis E (Incorrect Software Conversion Constant)**: Old software used a 5V ADC formula (e.g. `raw * (5.0 / 4095.0)`) instead of 3.3V, artificially inflating the voltage calculation.

---

## 2. ESP32 ADC Electrical Limits

| Parameter | Value | Impact / Rule |
| :--- | :--- | :--- |
| **Nominal Operating Rail ($V_{DD}$)** | 3.30 V | Logic high reference |
| **Absolute Maximum Rating ($V_{max}$)** | **3.60 V** ($V_{DD} + 0.3\text{V}$) | **Exceeding 3.6V causes ESD clamp breakdown and permanent chip destruction.** |
| **ADC Attenuation Mode** | **11 dB** (`ADC_11db`) | Extends full-scale measurement range up to ~3.1V |
| **Linear Measurement Window** | **150 mV to 2450 mV** | Highest precision region of the SAR ADC |
| **ADC Saturation Region** | **> 3.05 V (Raw > 4000)** | ADC clips at 4095; cannot differentiate between 3.2V and 5.0V! |
| **Software Over-Range Cutoff** | **3.05 V** | Firmware flags `STATUS_OVER_RANGE` and refuses to report false data |

---

## 3. Voltage Divider Engineering Calculations

To map a 0V–5.0V sensor output into the safe 0V–2.0V zone of the ESP32 ADC:

- **Top Resistor ($R_1$)**: $15\text{ k}\Omega \pm 1\%$
- **Bottom Resistor ($R_2$)**: $10\text{ k}\Omega \pm 1\%$ (tied to GND)

$$\alpha = \frac{R_2}{R_1 + R_2} = \frac{10000}{15000 + 10000} = 0.400$$

### Voltage Mapping Table:

| Sensor Board Output ($V_{sensor}$) | Voltage Divider Output ($V_{ADC}$) | ADC Pin (GPIO34 / GPIO32) Status |
| :---: | :---: | :--- |
| **0.00 V** | **0.00 V** | Minimum reading (or probe disconnected) |
| **1.00 V** | **0.40 V** | Safe (Linear region) |
| **2.50 V** | **1.00 V** | Safe (pH 7.00 neutral baseline) |
| **3.80 V** | **1.52 V** | Safe (Typical clear turbidity baseline) |
| **4.50 V** | **1.80 V** | Safe (Near maximum sensor rail) |
| **5.00 V** | **2.00 V** | **Maximum theoretical output from 5V board** |
| **> 7.50 V** | **> 3.00 V** | ⚠️ **DANGER / MISWIRING: ADC Saturation Knee** |
| **> 8.75 V** | **> 3.50 V** | 💥 **DESTRUCTION THRESHOLD for ESP32 Pin** |

---

## 4. Mandatory Hardware Commissioning Protocol (Multimeter First!)

Before connecting any analog signal wires to the ESP32 GPIO 34 or GPIO 32, execute this step-by-step verification using a **Digital Multimeter (DMM)**:

```
[ STEP 1 ] Verify Power Supply Rails
           • Set DMM to DC Volts (20V range).
           • Measure between ESP32 VIN and GND. Must be 4.8V to 5.2V.
           • Measure between ESP32 3V3 and GND. Must be 3.25V to 3.35V.

[ STEP 2 ] Verify Sensor Board Power
           • Measure voltage between pH board U+ and GND. Must be ~5.0V.
           • Measure voltage between Turbidity board VCC and GND. Must be ~5.0V.
           • If U+ or VCC reads > 5.5V, STOP IMMEDIATELY! Do not proceed.

[ STEP 3 ] Verify Voltage Divider Resistors with Power OFF
           • Unplug USB cable completely.
           • Switch DMM to Resistance (Ω) mode.
           • Measure resistance between Sensor Output (P / OUT) and the GPIO junction.
             Must measure ~15 kΩ.
           • Measure resistance between GPIO junction and Common Ground (GND).
             Must measure ~10 kΩ.
           • Measure resistance between Sensor Output and Ground.
             Must measure ~25 kΩ (15k + 10k in series).

[ STEP 4 ] Live Junction Verification (Signal Wire DISCONNECTED from ESP32)
           • Leave the jumper wires to GPIO 34 and GPIO 32 UNPLUGGED.
           • Plug in USB power.
           • Measure DC voltage at the 15kΩ/10kΩ divider junction with the probe in air / water.
           • Expected: 0.5V to 2.2V DC.
           • If the junction voltage exceeds 2.50V, DO NOT PLUG INTO ESP32!
             Recheck your resistor placement and ground wiring.

[ STEP 5 ] Secure Connection
           • Only after the junction is confirmed below 2.50V, power off, plug into
             GPIO 34 (pH) and GPIO 32 (Turbidity), and power on.
```

---

## 5. Software Over-Range Safeguards

The Phase 1 firmware implements strict, non-negotiable software safeguards in `SensorBase.h` and `SensorValidator.h`:

1. **Threshold Checks**:
   ```cpp
   if (rawAdc >= 4000 || adcVoltage >= 3.05f) {
       reading.status = STATUS_OVER_RANGE;
       reading.isValid = false;
       reading.calibratedValue = NAN;
   }
   ```
2. **Never Silently Clamp**: The firmware **never** forces an over-range voltage down to 3.3V and pretends it is a valid pH reading.
3. **Emergency Alert**: Triggers acoustic buzzer fault pattern (`PATTERN_FAULT`) and displays `ADC OVER-RANGE!` on the OLED display.
4. **Cloud Reporting**: ThingSpeak Field 7 sets bit 4 (`HEALTH_ADC_OVER_RANGE = 0x0010`) so backend and AI systems immediately detect the electrical anomaly.
