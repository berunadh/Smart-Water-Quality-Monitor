# Data Schema, Contract Specifications & Database Architecture

This document defines the data contracts and schema invariants shared across the **ESP32 Edge Firmware**, **ThingSpeak Cloud**, **Python FastAPI Backend**, **SQLite Database**, and **Phase 3 React Frontend**.

---

## 1. Unified Telemetry Data Contract

Every sensor reading record in the system complies with this unified schema:

| Field Name | Type | Nullable | Permitted Values | Engineering Description |
| :--- | :--- | :---: | :--- | :--- |
| `device_id` | `String` | No | e.g. `esp32-water-monitor-01` | Unique hardware identifier for the IoT node |
| `timestamp` | `DateTime` | No | ISO 8601 UTC | Telemetry timestamp from edge or cloud feed |
| `ph` | `Float` | **Yes** | `0.00` to `14.00` | Calibrated pH; **null if uncalibrated or in error** |
| `turbidity` | `Float` | **Yes** | $\ge 0.0$ NTU | Calibrated Turbidity; **null if uncalibrated or in error** |
| `tds` | `Float` | **Yes** | $\ge 0.0$ ppm | Calibrated TDS; **STRICTLY null until installed** |
| `ph_voltage` | `Float` | No | `0.000` to `5.000` V | Reconstructed green board output voltage ($V_{ADC} \times 2.50$) |
| `turbidity_voltage` | `Float` | No | `0.000` to `5.000` V | Reconstructed red board output voltage ($V_{ADC} \times 2.50$) |
| `ph_calibrated` | `Boolean` | No | `true` / `false` | True only if probe has undergone 2-point buffer calibration |
| `turbidity_calibrated` | `Boolean` | No | `true` / `false` | True only if probe has undergone clean water baseline calibration |
| `tds_calibrated` | `Boolean` | No | `false` in Phase 2 | TDS probe calibration flag (false until installed) |
| `alert_severity` | `Integer` | No | `0`, `1`, `2`, `3` | `0`=Normal, `1`=Warning, `2`=Critical, `3`=Fault |
| `alert_messages` | `String` | No | e.g. `ELEVATED TURBIDITY` | Active alert banner or warning description |
| `sensor_health_summary` | `String` | No | e.g. `OPERATIONAL` | Human-readable system state |
| `health_code` | `Integer` | No | 16-bit integer | Bitmask encoding hardware and network diagnostics |
| `data_source` | `String` | No | `thingspeak`, `simulated` | Origin of data: real cloud telemetry vs demo simulator |
| `operating_mode` | `String` | No | `real`, `demo` | Active system mode |
| `is_valid` | `Boolean` | No | `true` / `false` | False if reading violates electrical or physical bounds |
| `is_stale` | `Boolean` | No | `true` / `false` | True if reading age exceeds 300 seconds |

---

## 2. Special State Handling Rules

### A. Missing TDS Sensor
- **Rule**: TDS is currently uninstalled.
- **Handling**:
  - In ESP32 Firmware: `&field3=` is completely omitted from the HTTP POST payload.
  - In ThingSpeak: Stored as `""` (empty string) / null.
  - In Python Backend: Deserialized strictly to Python `None` and JSON `null`.
  - **Forbidden**: Never write `0.0 ppm` to represent missing TDS.

### B. Uncalibrated pH / Turbidity
- **Rule**: Probes requiring buffer or baseline calibration must not report fabricated numbers.
- **Handling**:
  - Physical measurement fields (`ph`, `turbidity`) are `null`.
  - Calibration flags (`ph_calibrated`, `turbidity_calibrated`) are `false`.
  - Reconstructed voltages (`ph_voltage`, `turbidity_voltage`) are reported honestly.

### C. Stale Telemetry
- If the duration between the latest reading's timestamp and the current server time exceeds **300 seconds (5 minutes)**:
  - `is_stale` is set to `true`.
  - System health reports `data_freshness: "STALE"`.
  - Cloud failure is logged, but local firmware continues monitoring and alarming independently.

---

## 3. SQLite Database Schema & Tables

The SQLite database (`water_quality.db`) contains four optimized relational tables:

### Table 1: `water_readings`
Stores continuous time-series telemetry.
```sql
CREATE TABLE water_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER UNIQUE,               -- ThingSpeak entry ID (null for demo)
    device_id VARCHAR(64) NOT NULL,
    timestamp DATETIME NOT NULL,
    ph FLOAT,
    turbidity FLOAT,
    tds FLOAT,
    ph_voltage FLOAT NOT NULL,
    turbidity_voltage FLOAT NOT NULL,
    ph_calibrated BOOLEAN NOT NULL,
    turbidity_calibrated BOOLEAN NOT NULL,
    tds_calibrated BOOLEAN NOT NULL,
    alert_severity INTEGER NOT NULL,
    health_code INTEGER NOT NULL,
    sensor_health_summary VARCHAR(64) NOT NULL,
    alert_messages VARCHAR(255) NOT NULL,
    data_source VARCHAR(32) NOT NULL,
    operating_mode VARCHAR(16) NOT NULL,
    is_valid BOOLEAN NOT NULL,
    is_stale BOOLEAN NOT NULL,
    validation_notes VARCHAR(255)
);

CREATE INDEX idx_reading_device_time ON water_readings (device_id, timestamp);
CREATE INDEX idx_reading_valid_time ON water_readings (is_valid, timestamp);
```

### Table 2: `alert_logs`
Logs threshold breaches, electrical over-range events, and incident resolution.
```sql
CREATE TABLE alert_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    severity INTEGER NOT NULL,
    title VARCHAR(64) NOT NULL,
    message VARCHAR(255) NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT 0,
    resolved_at DATETIME
);

CREATE INDEX idx_alert_time_resolved ON alert_logs (resolved, timestamp);
```

### Table 3: `ml_anomalies`
Persists detected statistical, multivariate, and hardware anomalies.
```sql
CREATE TABLE ml_anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    parameter VARCHAR(32) NOT NULL,
    measured_value FLOAT,
    baseline_mean FLOAT,
    baseline_std FLOAT,
    anomaly_score FLOAT NOT NULL,
    detector_type VARCHAR(32) NOT NULL,
    anomaly_type VARCHAR(64) NOT NULL,
    human_explanation VARCHAR(255) NOT NULL
);

CREATE INDEX idx_anomaly_param_time ON ml_anomalies (parameter, timestamp);
```

### Table 4: `chat_messages`
Stores user queries, model responses, and audit logs.
```sql
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id VARCHAR(64) NOT NULL,
    timestamp DATETIME NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    model_used VARCHAR(64),
    source VARCHAR(32) NOT NULL
);
```

---

## 4. 16-Bit System Health Bitmask Encoding

Bitmask mapping uploaded in ThingSpeak Field 7 and decoded by the backend:

| Bit | Constant | Hex | Description |
| :---: | :--- | :---: | :--- |
| **0** | `HEALTH_WIFI_DISCONNECTED` | `0x0001` | ESP32 Wi-Fi radio offline or disconnected |
| **1** | `HEALTH_CLOUD_ERROR` | `0x0002` | ThingSpeak HTTP POST timeout or rejected (rate limit) |
| **2** | `HEALTH_PH_FAULT` | `0x0004` | pH electrode disconnected (~0V) or stuck output |
| **3** | `HEALTH_TURB_FAULT` | `0x0008` | Turbidity optical probe disconnected or stuck output |
| **4** | `HEALTH_ADC_OVER_RANGE` | `0x0010` | **ELECTRICAL HAZARD**: Voltage divider output $>3.05\text{V}$ |
| **5** | `HEALTH_TDS_UNAVAILABLE` | `0x0020` | TDS hardware probe absent / pending installation |
| **6** | `HEALTH_CALIBRATION_PENDING` | `0x0040` | pH or Turbidity requires standard solution calibration |
| **7** | `HEALTH_DEMO_MODE_ACTIVE` | `0x0080` | Telemetry is explicitly simulated for testing |
