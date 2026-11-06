# System Architecture & Multi-Phase Roadmap

```mermaid
flowchart TD
    subgraph Edge["Layer 1: ESP32 Edge Firmware (Phase 1)"]
        PH["pH Sensor (GPIO34)"] --> ADC_FILT["ADC Oversampling & Trimmed Mean Filter"]
        TURB["Turbidity Sensor (GPIO32)"] --> ADC_FILT
        TDS["TDS Sensor (GPIO35 Reserved)"] -.-> ADC_FILT
        
        ADC_FILT --> VALIDATOR["Sensor Validator & Electrical Boundary Checks"]
        VALIDATOR --> OLED["SSD1306 OLED (128x64 I2C)"]
        VALIDATOR --> BUZZER["Acoustic Buzzer (GPIO25 Non-Blocking)"]
        VALIDATOR --> CLOUD_CLIENT["ThingSpeak HTTP Client (WiFi.h)"]
    end

    subgraph Cloud["Layer 2: Cloud Ingestion (Phase 1 Ready)"]
        CLOUD_CLIENT -- "HTTP POST (Fields 1-7 every 20s)" --> TS["ThingSpeak Telemetry Channel"]
    end

    subgraph Backend["Layer 3: Python Backend Services (Phase 2)"]
        TS -- "HTTP REST GET feeds.json" --> TS_SYNC["ThingSpeak Ingestion Service"]
        TS_SYNC --> PY_VALID["Python Data Integrity & Safety Validator"]
        PY_VALID --> DB[(SQLite Database: water_quality.db)]
        
        DB --> API["FastAPI Application Server (:8000)"]
    end

    subgraph AI_ML["Layer 4: AI & Machine Learning Pipeline (Phase 2)"]
        DB --> FEAT["Feature Pipeline (Rolling Mean, Std, Drift)"]
        FEAT --> ANOMALY["Statistical Z-Score & Isolation Forest Anomaly Detectors"]
        FEAT --> TREND["Trend Analyzer (Linear Drift & Baseline Shift)"]
        API --> CHATBOT["AquaAdvisor AI Agent (Gemini LLM + Domain Tools)"]
    end

    subgraph Frontend["Layer 5: Web Dashboard (Phase 3)"]
        API -- "REST API / WebSockets" --> REACT["React 18 + Vite Web Dashboard"]
    end
```

---

## 1. Architectural Layers & Responsibilities

### Layer 1: ESP32 Edge Firmware (Embedded C++)
- **Core Role**: Physical sensor acquisition, noise filtering, electrical over-range safety checks, and immediate local acoustic/visual warning.
- **Fail-Safe Design**: Operates 100% autonomously without requiring an active internet connection or server. If Wi-Fi disconnects or ThingSpeak drops, sensor sampling, OLED status display, and buzzer alerts continue uninterrupted.

### Layer 2: Cloud Telemetry Channel (ThingSpeak)
- Serves as an intermediary cloud buffer between the edge microcontroller and the Python application backend.
- Stores continuous time-series telemetry structured according to our 7-field data contract:
  - `field1`: Calibrated pH
  - `field2`: Calibrated Turbidity (NTU)
  - `field3`: Calibrated TDS (ppm, reserved)
  - `field4`: Alert Severity (0=Normal, 1=Warning, 2=Critical, 3=Sensor Fault)
  - `field5`: pH Board Output Voltage ($V_{board}$)
  - `field6`: Turbidity Board Output Voltage ($V_{board}$)
  - `field7`: System Health Bitmask (16-bit integer)

### Layer 3: Python Backend Services (FastAPI + SQLite)
- **Core Role**: Ingests cloud telemetry, enforces schema contracts, computes aggregate statistics, and provides clean REST endpoints for dashboards and analytical models.
- **Data Quality Invariants**: Validates that uninstalled sensors (TDS) are never stored as zero, checks for ADC saturation, and flags electrical hazards.

### Layer 4: AI & Machine Learning Pipeline
- **Anomaly Detection**: Moving statistical Z-Score detector flags abrupt pipe flushing, particulate spikes, or chemical anomalies. Unsupervised Isolation Forest is prepared for multivariate patterns.
- **Trend Analysis**: Computes linear drift rates (e.g. gradual filter degradation or seasonal temperature shifts).
- **AI Chatbot**: AquaAdvisor provides conversational explanations of EPA/WHO standards and apartment plumbing diagnostics.

### Layer 5: Web UI (React & Vite Dashboard - Phase 3)
- Real-time telemetry monitoring, historical chart inspection, alert resolution, and interactive AI chatbot interface.

---

## 2. Telemetry Contract Matrix

| Field | Parameter | Engineering Units | Permitted Values | Handling when Uncalibrated / Absent |
| :---: | :--- | :---: | :---: | :--- |
| **Field 1** | pH | pH scale (0–14) | 0.00 to 14.00 | Omitted (empty string); never fabricated |
| **Field 2** | Turbidity | NTU | $\ge 0.0$ NTU | Omitted (empty string); never fabricated |
| **Field 3** | TDS | ppm | $\ge 0.0$ ppm | **Omitted / Blank (STRICT: NEVER 0.0)** |
| **Field 4** | Alert Severity | Integer Enum | 0, 1, 2, 3 | 0=Normal, 1=Warning, 2=Critical, 3=Fault |
| **Field 5** | pH Board Voltage | Volts (V) | 0.000 to 5.000 V | Reconstructed board voltage ($V_{ADC} \times 2.50$) |
| **Field 6** | Turbidity Board Voltage | Volts (V) | 0.000 to 5.000 V | Reconstructed board voltage ($V_{ADC} \times 2.50$) |
| **Field 7** | System Health Code | 16-bit Bitmask | Bit 0 through 7 | Encodes Wi-Fi, Cloud, Fault, and Safety states |
