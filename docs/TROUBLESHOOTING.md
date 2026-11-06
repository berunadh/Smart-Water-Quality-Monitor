# Troubleshooting & Hardware Diagnostics Guide

This guide addresses common hardware, electrical, network, and firmware issues encountered during development.

---

## 1. Electrical & ADC Anomalies

### Issue: Firmware logs `ADC OVER-RANGE!` or OLED shows `SAFETY: DANGER (>3.05V)`
- **Symptom**: Serial monitor prints `[SAFETY ALARM] ELECTRICAL OVER-RANGE DETECTED! ADC > 3.05V!`.
- **Root Cause**:
  1. The $10\text{ k}\Omega$ resistor ground leg is disconnected or loose on the breadboard.
  2. The $15\text{ k}\Omega$ and $10\text{ k}\Omega$ resistors are reversed.
  3. The sensor board is connected to an external supply higher than 5V (e.g. 9V or 12V).
  4. The analog signal wire was plugged directly into the ESP32 pin bypassing the divider.
- **Solution**:
  - Unplug the jumper wire from GPIO 34 / GPIO 32 immediately.
  - Follow the [Multimeter Commissioning Protocol](file:///Users/berunadh/Desktop/projects/O3_S1_TBP/Smart-Water-Quality-Monitor/docs/ELECTRICAL_SAFETY.md).
  - Verify with a multimeter that resistance between the junction and GND is exactly $10\text{ k}\Omega$ and junction voltage never exceeds 2.2V.

### Issue: ADC readings fluctuate wildly or float near 3.0V with probe in air
- **Symptom**: Unconnected probe causes random jumping values.
- **Root Cause**: ESP32 GPIO 34 and GPIO 35 are high-impedance, input-only CMOS pins without internal pull-ups or pull-downs. An open circuit acts as an antenna picking up mains electromagnetic noise.
- **Solution**:
  - Connect the $15\text{ k}\Omega / 10\text{ k}\Omega$ divider to ground. The $10\text{ k}\Omega$ resistor to ground naturally drains capacitive charge when unplugged.
  - Submerge the probe in water or connect the BNC electrode securely.

---

## 2. OLED Display Issues

### Issue: OLED remains completely dark / blank on startup
- **Symptom**: Serial monitor logs `WARNING: OLED SSD1306 initialization failed`.
- **Checklist**:
  1. **I2C Pin Check**: Verify SDA is on **GPIO 21** and SCL is on **GPIO 22**.
  2. **I2C Address**: Most 0.96" SSD1306 displays use address `0x3C`. Some cheaper clones use `0x3D`. Check the address resistor on the back of the OLED module.
  3. **Power Pin**: Verify the OLED VCC pin is connected to **3V3** (not 5V, unless the module has an onboard 3.3V LDO regulator).
  4. **Loose Breadboard Jumpers**: Breadboard tie-points frequently develop intermittent contact. Try replacing the 4 jumper wires.

---

## 3. Buzzer Subsystem Issues

### Issue: Buzzer makes a continuous, loud blaring sound on boot
- **Root Cause**: Some buzzer modules use a PNP transistor driver (active-low) instead of NPN (active-high).
- **Solution**:
  - In `firmware/water_monitor/config.h`, change:
    ```cpp
    #define BUZZER_ACTIVE_LOW true
    ```
  - Recompile and upload firmware.

### Issue: Buzzer produces only a faint "click" instead of a tone
- **Root Cause**: The buzzer is a **passive transducer** (requiring an AC oscillating square wave like `ledcWriteTone` or `tone()`), whereas active buzzers have an internal oscillator and only require a DC logic HIGH.
- **Solution**: Ensure your module is an **active buzzer** (has a black epoxy seal on the bottom and produces sound when connected directly across 3.3V/5V and GND).

---

## 4. Wi-Fi & Cloud Telemetry Issues

### Issue: ESP32 fails to connect to Wi-Fi (`WiFi: OFF` or `WiFi: NO_CFG`)
- **Symptom**: Serial monitor outputs `[WIFI] Disconnected. Reconnecting...`.
- **Checklist**:
  1. **2.4 GHz vs 5.0 GHz**: The classic ESP32 **only supports 2.4 GHz Wi-Fi (802.11 b/g/n)**. It cannot detect 5 GHz networks. Ensure your router broadcasts an active 2.4 GHz SSID.
  2. **Credentials in secrets.h**: Open `firmware/water_monitor/secrets.h` and confirm the SSID and password match your network exactly (case-sensitive).
  3. **USB Power Sag**: The ESP32 Wi-Fi radio draws brief current spikes up to ~250 mA during RF packet transmission. Ensure your Mac USB port or USB hub provides adequate power.

### Issue: ThingSpeak returns HTTP Code 0 or entry ID 0 (`Cld: RATE` or `Cld: ERR`)
- **Symptom**: Serial logs `[CLOUD] ThingSpeak rate limit or rejected. Response: 0`.
- **Root Cause**: ThingSpeak's free tier strictly limits channel uploads to **once every 15 seconds**.
- **Solution**:
  - The firmware default is `THINGSPEAK_INTERVAL_MS = 20000` (20 seconds).
  - Do not lower this interval below 15000 ms.
  - Verify that the `THINGSPEAK_WRITE_API_KEY` in `secrets.h` is the **Write API Key** (not the Read API Key).

---

## 5. TDS Sensor Status

### Issue: OLED displays `TDS: N/A (PENDING)`
- **Explanation**: This is **by design**. As requested, the TDS hardware has not arrived and is strictly kept disabled (`FEATURE_TDS_ENABLED = false`).
- The firmware will **never** report false 0.0 ppm values for uninstalled hardware.
- Once the physical TDS sensor arrives in Phase 2, connect it to reserved **GPIO 35** and enable it in `config.h`.
