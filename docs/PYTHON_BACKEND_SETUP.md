# Python FastAPI Backend Setup & Operational Guide (macOS)

This guide provides step-by-step instructions for running, configuring, testing, and developing the **Python FastAPI Backend** on **macOS Apple Silicon (M-series MacBook Air)**.

---

## 1. System Requirements & Architecture

- **Machine**: Apple Silicon Mac (M1/M2/M3/M4/M5) running macOS.
- **Python**: Python 3.9+ (System Python 3.9.6 or Homebrew Python).
- **RAM**: Runs lightweight in under 150 MB RAM (easily fits in 16 GB).
- **Architecture**:
  - Web Server: Uvicorn ASGI server running FastAPI.
  - Database: Local SQLite database (`water_quality.db`) with SQLAlchemy ORM.
  - Ingestion: Async HTTP client (`httpx`) retrieving ThingSpeak feeds.
  - Analytics: Scikit-learn, NumPy, and Pandas.

---

## 2. Virtual Environment Setup & Installation

From the project root:

```bash
# 1. Navigate to the project directory
cd /Users/berunadh/Desktop/projects/O3_S1_TBP/Smart-Water-Quality-Monitor

# 2. Create the Python virtual environment
python3 -m venv backend/venv

# 3. Activate the virtual environment
source backend/venv/bin/activate

# 4. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

---

## 3. Environment Configuration (`.env`)

The backend reads configuration from `backend/.env`.

### A. Demo Mode (Default — No ESP32 or Cloud Keys Required)
Use this mode when developing on your Mac without physical sensors:
```bash
DATA_MODE=demo
DEVICE_ID=esp32-water-monitor-01
THINGSPEAK_CHANNEL_ID=0
THINGSPEAK_READ_API_KEY=
POLL_INTERVAL_SECONDS=20
DATABASE_URL=sqlite:///./water_quality.db
THRESHOLD_PH_MIN=6.5
THRESHOLD_PH_MAX=8.5
THRESHOLD_TURBIDITY_NTU_MAX=5.0
THRESHOLD_TDS_PPM_MAX=500.0
LLM_PROVIDER=fallback
LLM_MODEL=gemini-2.5-flash
LLM_API_KEY=
```

### B. Real Mode (Live ThingSpeak Ingestion)
When your ESP32 is deployed and uploading to your ThingSpeak channel:
```bash
DATA_MODE=real
DEVICE_ID=esp32-water-monitor-01
THINGSPEAK_CHANNEL_ID=YOUR_NUMERIC_CHANNEL_ID
THINGSPEAK_READ_API_KEY=YOUR_16_CHAR_READ_API_KEY
POLL_INTERVAL_SECONDS=20
DATABASE_URL=sqlite:///./water_quality.db
THRESHOLD_PH_MIN=6.5
THRESHOLD_PH_MAX=8.5
THRESHOLD_TURBIDITY_NTU_MAX=5.0
THRESHOLD_TDS_PPM_MAX=500.0

# Optional: Add Google Gemini or OpenAI API Key for Hosted LLM Chatbot
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
LLM_API_KEY=YOUR_GEMINI_API_KEY
```

---

## 4. Starting the FastAPI Server

Ensure your virtual environment is active, then launch the ASGI server:

```bash
# From the project root
./backend/venv/bin/uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

### Output:
```text
INFO:     Started server process [83921]
INFO:     Waiting for application startup.
INFO:     === Starting Smart Apartment Water Quality Monitor v2.0.0-phase2 [development] ===
INFO:     [Config] Operating Mode: DEMO
INFO:     [Database] SQLite database schema initialized.
INFO:     [DemoService] Successfully seeded 60 demo records.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

## 5. Interactive Swagger UI & API Endpoints

Open your browser to explore and execute all API routes interactively:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Key Endpoints:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Backend health, cloud connectivity, last sync timestamp |
| `GET` | `/api/system/status` | Decoded 16-bit hardware bitmask, sensor status, Wi-Fi |
| `GET` | `/api/readings/latest` | Most recent telemetry reading with voltages & data source |
| `GET` | `/api/readings/history?limit=50` | Historical time-series telemetry |
| `GET` | `/api/readings/statistics?hours=24` | Mean, min, max summary over 24 hours |
| `GET` | `/api/alerts` | Active warnings, critical alerts, and incident summary |
| `GET` | `/api/ml/anomalies` | Multi-tier anomaly detection (MAD + Isolation Forest + Faults) |
| `GET` | `/api/ml/trends` | Linear trend regression slopes and R² baseline drift |
| `GET` | `/api/ml/summary` | Categorized AI insights (FACT, ANOMALY, PREDICTION, WARNING) |
| `POST` | `/api/chat` | AI Water Quality Advisor conversational query |
| `POST` | `/api/demo/inject/{scenario}` | Inject `warning`, `critical`, or `sensor_fault` test events |
| `POST` | `/api/thingspeak/sync` | Trigger immediate cloud telemetry sync |

---

## 6. Running the Test Suite

Execute the complete pytest test suite:

```bash
./backend/venv/bin/pytest backend/tests -v
```

All 47 tests execute in ~1.2 seconds, validating:
- ThingSpeak feed parsing & duplicate prevention.
- Missing TDS null integrity (never coerced to 0.0).
- Electrical safety limits (ADC > 3.05V rejected).
- Scikit-learn Isolation Forest & MAD anomaly detectors.
- Hardware stuck value & disconnected probe fault detectors.
- Linear trend regression slopes.
- Demo mode scenario generation.
- Chatbot context retrieval and fallback rule-based advisor.
