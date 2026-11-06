# Smart Apartment Water Quality Monitor

[![Firmware Build Check](https://img.shields.io/badge/ESP32%20Firmware-Compiled%20Clean-success.svg)](#firmware-compilation)
[![Architecture](https://img.shields.io/badge/Architecture-Modular%20IoT%20%2B%20AI-blue.svg)](#project-architecture)
[![Phase](https://img.shields.io/badge/Project%20Phase-Phase%201%20Complete-green.svg)](#phase-breakdown)

An intelligent, full-stack IoT and AI-enabled water quality monitoring system designed for modern apartments and residential buildings. The system continuously measures water parameters, provides immediate local audio-visual alerts, uploads telemetry to cloud infrastructure, and enables machine learning anomaly detection and AI conversational advisory services.

---

## 1. Project Overview & Multi-Phase Roadmap

The project is structured into three distinct phases:

- **Phase 1 (Completed)**:
  - High-reliability ESP32 embedded firmware (Arduino C++).
  - Multi-sensor acquisition: E201-C pH electrode and optical turbidity sensor.
  - Architecture prepared for future TDS expansion (reserved on GPIO 35).
  - Electrical safety engineering & voltage divider verification ($15\text{ k}\Omega / 10\text{ k}\Omega$).
  - I2C SSD1306 OLED multi-page dashboard & acoustic non-blocking buzzer alert engine.
  - ThingSpeak cloud telemetry integration prepared (Fields 1–7 data contract).
  - Production-ready Python backend and AI/ML module structure.
  - Comprehensive documentation, schematics, and verification scripts.
- **Phase 2 (Next Step)**:
  - Python FastAPI backend execution and SQLite database storage.
  - Automated ThingSpeak cloud synchronization worker.
  - Machine learning anomaly detection (Z-Score + Isolation Forest) and trend drift analysis.
  - AI Water Quality Advisor chatbot integration with Google Gemini.
- **Phase 3**:
  - React & Vite interactive web dashboard with real-time charts and alert management.

---

## 2. Hardware Specifications

| Component | Specification | Connection Details | Role in Phase 1 |
| :--- | :--- | :--- | :--- |
| **Microcontroller** | ESP32-D0WD-V3 (ESP32 Dev Module) | USB-C on macOS | Core edge controller & local alerting |
| **pH Sensor** | E201-C BNC Electrode + Green Board | GPIO 34 via 15kΩ/10kΩ divider | Analog acquisition & 2-point calibration |
| **Turbidity Sensor** | Optical Probe + Red Board | GPIO 32 via 15kΩ/10kΩ divider | Analog acquisition & clear water baseline |
| **TDS Sensor** | *Hardware Not Arrived* | GPIO 35 (Reserved) | Strict N/A handling; disabled until physically present |
| **OLED Display** | SSD1306 128×64 Monochrome | I2C (SDA=21, SCL=22, 0x3C) | Real-time dashboard & electrical diagnostics |
| **Audio Buzzer** | Active/Passive Buzzer Module | GPIO 25 (Signal) | Non-blocking acoustic alert patterns |
| **Host Machine** | Apple Silicon M5 MacBook Air | macOS, 16 GB RAM | Development, compilation, & backend host |

---

## 3. Electrical Safety & Voltage Dividers

> [!CAUTION]
> **ELECTRICAL SAFETY INVARIANT**: The ESP32 ADC pins operate at 3.3V logic with an absolute maximum rating of 3.6V. Any input exceeding 3.6V risks permanent chip destruction.

Both analog sensors output 0V to 5.0V signals. Identical resistor dividers step down the voltages safely to a 0V–2.0V window:

$$\alpha = \frac{10\text{ k}\Omega}{15\text{ k}\Omega + 10\text{ k}\Omega} = 0.400 \implies V_{ADC} = V_{sensor} \times 0.400$$

### Analysis of Previous Software Log (`3.134V` ADC / `7.835V` Estimated):
- If the sensor board is powered by 5V, it cannot physically generate 7.835V.
- The 3.134V reading indicated either:
  1. An open ground on the 10kΩ resistor (passing un-attenuated voltage to GPIO 34),
  2. Reversed resistor positions ($R_1 = 10\text{k}\Omega, R_2 = 15\text{k}\Omega$),
  3. External supply over-voltage (>5V), or
  4. A floating ADC pin.
- **Firmware Safeguard**: The firmware detects any voltage $\ge 3.05\text{V}$ (`ADC_OVER_RANGE`), immediately halts valid data output, triggers an acoustic alarm, and flags bit 4 (`HEALTH_ADC_OVER_RANGE`) in cloud telemetry.
- **Mandatory Procedure**: Follow the [Multimeter Commissioning Guide](file:///Users/berunadh/Desktop/projects/O3_S1_TBP/Smart-Water-Quality-Monitor/docs/ELECTRICAL_SAFETY.md) before plugging analog wires into the ESP32.

---

## 4. Directory Structure

```text
Smart-Water-Quality-Monitor/
├── firmware/
│   └── water_monitor/
│       ├── water_monitor.ino         # Main non-blocking loop & CLI interpreter
│       ├── config.h                  # Hardware pins, thresholds, & safety constants
│       ├── secrets.example.h         # Credentials template
│       ├── secrets.h                 # Local Wi-Fi & ThingSpeak keys (git-ignored)
│       ├── sensors/
│       │   ├── SensorBase.h          # Abstract base, trimmed mean, & boundary checks
│       │   ├── PHSensor.h            # E201-C driver with 2/3-point calibration
│       │   ├── TurbiditySensor.h     # Optical driver with baseline calibration
│       │   ├── TDSSensor.h           # Reserved interface (reports NULL, never 0)
│       │   └── SensorValidator.h     # Health bitmask & severity evaluator
│       ├── display/
│       │   └── DisplayManager.h      # SSD1306 OLED multi-page manager
│       ├── alerts/
│       │   └── AlertManager.h        # Non-blocking buzzer state machine
│       └── cloud/
│           └── CloudManager.h        # Wi-Fi client & ThingSpeak HTTP updater
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI application entrypoint
│   │   ├── core/                     # Configuration, settings, & logging
│   │   ├── database/                 # SQLAlchemy session & SQLite engine
│   │   ├── models/                   # Water readings & alert database models
│   │   ├── schemas/                  # Pydantic request/response schemas
│   │   ├── services/                 # ThingSpeak sync, validation, & alerts
│   │   ├── ml/                       # Anomaly detectors, trend regression, pipeline
│   │   ├── chatbot/                  # AquaAdvisor AI agent & domain tools
│   │   └── api/v1/                   # REST API routes (sensors, alerts, health, etc.)
│   ├── tests/                        # Comprehensive unit & contract tests
│   ├── requirements.txt              # Python dependencies
│   └── .env.example                  # Environment configuration template
├── frontend/
│   └── README.md                     # Phase 3 React dashboard architecture
├── docs/
│   ├── HARDWARE_PINOUT.md            # Pinout table & ADC1 vs ADC2 rationale
│   ├── WIRING_DIAGRAM.md             # Schematics & breadboard connections
│   ├── ELECTRICAL_SAFETY.md          # In-depth electrical limits & multimeter protocol
│   ├── ARDUINO_SETUP_MACOS.md        # Arduino IDE 2.x setup for Apple Silicon
│   ├── CALIBRATION_GUIDE.md          # 2-point buffer & turbidity calibration
│   ├── TROUBLESHOOTING.md            # Hardware & networking diagnostic guide
│   └── ARCHITECTURE.md               # System architecture & telemetry contracts
├── scripts/
│   └── compile_firmware.sh           # Automated Arduino CLI build script
├── .gitignore                        # Secrets & build artifact exclusions
└── README.md                         # Master documentation
```

---

## 5. Quickstart & Verification

### A. Verifying & Compiling Firmware (macOS)
The repository includes an automated verification script that locates the Arduino CLI bundled with Arduino IDE and compiles the sketch:

```bash
# From the project root
./scripts/compile_firmware.sh
```

**Compilation Result**:
```text
Sketch uses 1,077,512 bytes (82%) of program storage space.
Global variables use 50,792 bytes (15%) of dynamic memory.
[✓] BUILD SUCCESSFUL! Firmware compiles cleanly with 0 errors.
```

### B. Running Backend Contract & Safety Tests
Verify electrical formulas, data contracts, and missing TDS handling:

```bash
python3 backend/tests/test_validation_unittest.py
```

**Test Output**:
```text
Ran 5 tests in 0.000s
OK
```

---

## 6. Telemetry Contract (ThingSpeak Fields)

The ESP32 firmware transmits HTTP POST requests every 20 seconds formatted as follows:

| Field | Parameter | Value Format | Behavior when Uncalibrated / Absent |
| :---: | :--- | :--- | :--- |
| **Field 1** | pH | Float (e.g. `7.35`) | Omitted from payload; never fabricated |
| **Field 2** | Turbidity | Float (e.g. `1.8`) | Omitted from payload; never fabricated |
| **Field 3** | TDS | Float | **Omitted / Blank (Strict: NEVER 0.0)** |
| **Field 4** | Alert Severity | Integer (`0` to `3`) | `0`=Normal, `1`=Warning, `2`=Critical, `3`=Fault |
| **Field 5** | pH Board Voltage | Float (e.g. `2.450`) | Uncalibrated diagnostic board voltage |
| **Field 6** | Turbidity Board Voltage | Float (e.g. `4.120`) | Uncalibrated diagnostic board voltage |
| **Field 7** | System Health Code | 16-bit Integer | Encodes Wi-Fi, sensor faults, & over-range |

---

## 7. Interactive Serial Bench Calibration

The firmware includes an interactive CLI accessible via the Arduino IDE Serial Monitor (115200 baud):

- `help` — Show available commands.
- `status` — Dump live ADC voltages, reconstructed voltages, and health code.
- `cal_ph7` — Register current probe voltage as pH 7.00 neutral baseline.
- `cal_ph4` — Register current probe voltage as pH 4.01 acidic baseline.
- `cal_turb_clear` — Register current turbidity probe voltage as 0 NTU clear baseline.
- `cal_reset` — Reset calibrations back to `CALIBRATION PENDING`.

---

## 8. Exact Next Steps for Phase 2

1. **Physical Multimeter Verification**: Follow `docs/ELECTRICAL_SAFETY.md` on the physical breadboard to confirm divider voltages never exceed 2.2V.
2. **Flash ESP32**: Upload the compiled sketch to the physical ESP32 and verify OLED boot splash and startup beep.
3. **ThingSpeak Setup**: Create a free ThingSpeak channel, add Write API key to `secrets.h`, and observe live data upload.
4. **Backend Ingestion**: Launch the FastAPI server (`uvicorn app.main:app --reload`), configure `.env` with the ThingSpeak Channel ID, and test `/api/v1/thingspeak/sync`.
5. **AI Advisor Activation**: Add Gemini API key to `.env` to enable conversational water quality queries via `/api/v1/chatbot/query`.
