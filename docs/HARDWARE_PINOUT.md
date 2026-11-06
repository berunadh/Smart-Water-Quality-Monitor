# Hardware Pinout & Peripheral Configuration Guide

**Microcontroller**: ESP32 Development Board (ESP32-D0WD-V3)  
**Target Board**: ESP32 Dev Module  
**Core**: Classic ESP32 Arduino Core  

---

## 1. Pin Assignment Table

| Subsystem | Peripheral / Device | Board Pin | ESP32 GPIO | Channel / Function | Signal Type | Voltage Divider | Direction |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **pH Sensor** | Green Signal Board (P pin) | P | **GPIO 34** | ADC1_CH6 | Analog In (0–2.0V) | 15kΩ (top) / 10kΩ (GND) | Input Only |
| **Turbidity Sensor** | Red Signal Board (OUT pin) | OUT | **GPIO 32** | ADC1_CH4 | Analog In (0–2.0V) | 15kΩ (top) / 10kΩ (GND) | Analog In |
| **TDS Sensor** | *Future Expansion (Uninstalled)* | Signal | **GPIO 35** | ADC1_CH7 | Analog In (Reserved) | Pending Arrival | Input Only |
| **OLED Display** | SSD1306 128×64 I2C | SDA | **GPIO 21** | Wire I2C SDA | Digital (3.3V) | None (Internal/Module Pullup) | Bidirectional |
| **OLED Display** | SSD1306 128×64 I2C | SCL | **GPIO 22** | Wire I2C SCL | Digital (3.3V) | None (Internal/Module Pullup) | Output |
| **Buzzer** | Active/Passive Buzzer Module | S (Signal) | **GPIO 25** | DAC1 / GPIO | Digital (3.3V) | Direct driver / Transistor | Output |
| **Power Supply** | Common Ground | GND | **GND** | System GND | 0V Reference | Common Ground Bus | Power |
| **Power Supply** | Sensor Supply (U+, VCC) | VCC / U+ | **VIN / 5V** | 5V Rail (USB) | +5V DC | From USB 5V (or regulated) | Power Out |
| **Display Power** | OLED Supply | VCC | **3V3** | 3.3V Rail | +3.3V DC | From ESP32 LDO | Power Out |

---

## 2. Engineering Justification: ADC1 vs ADC2

A critical design requirement on the ESP32 is avoiding **ADC2** when Wi-Fi is active.

```
       ESP32 ADC SUBSYSTEM
   ┌────────────────────────────────────────┐
   │ ADC1: GPIO 32, 33, 34, 35, 36, 39      │ ──> SAFE TO USE WITH WI-FI
   │ (Dedicated hardware SAR ADC)           │     (pH on 34, Turb on 32, TDS on 35)
   ├────────────────────────────────────────┤
   │ ADC2: GPIO 0, 2, 4, 12, 13, 14, 15,    │ ──> SHARED WITH WI-FI ENGINE!
   │       25, 26, 27                       │     analogRead() fails while Wi-Fi
   │                                        │     transmits. DO NOT USE FOR SENSORS!
   └────────────────────────────────────────┘
```

- **GPIO 34 and GPIO 35** are input-only pins (no internal pull-up/pull-down resistors). This makes them electrically optimal for high-impedance analog sensor signals without parasitic resistor loading.
- **GPIO 32** is also on ADC1, ensuring continuous, glitch-free analog sampling during Wi-Fi transmissions to ThingSpeak.
- **GPIO 25** is a general-purpose output pin on RTC/DAC, completely safe for driving the buzzer transistor/driver.

---

## 3. Power Rail Allocation

| Rail | Voltage | Destination Modules | Current Budget (Estimated) |
| :--- | :--- | :--- | :--- |
| **3V3** | 3.3V DC (ESP32 LDO) | SSD1306 OLED, ESP32 Chip | ~20 mA (OLED) + ~150-240 mA (ESP32 Wi-Fi peak) |
| **VIN / 5V** | 5.0V DC (USB Bus) | Green pH Board (U+), Red Turbidity Board (VCC) | ~30 mA (Turbidity IR LED) + ~10 mA (pH Op-Amp) |
| **GND** | 0.0V Ground | All boards & voltage dividers | Common ground reference across all modules |

> [!CAUTION]
> **Common Ground Requirement**: The ground pins of the ESP32, the pH board, the turbidity board, and the two 10kΩ voltage divider bottom legs **must all be firmly tied to a single common ground rail**. An open ground connection will cause divider voltages to float up to 5V, risking permanent destruction of the ESP32 ADC!
