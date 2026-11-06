# Phase 3 — React Web Dashboard (Architecture & Roadmap)

This directory is reserved for the **Phase 3** React & Vite modern web dashboard.

## Objectives
1. **Live Water Quality Dashboard**: Real-time display of pH, Turbidity, and future TDS.
2. **Interactive Time-Series Charts**: Recharts / Chart.js showing hourly, daily, and weekly parameter trends.
3. **Alert Center**: Visual notification banners with sound toggle, severity badges, and acknowledgment logs.
4. **AI Advisor Chat Interface**: Conversational UI to query AquaAdvisor (backed by FastAPI and Google Gemini).
5. **System & Electrical Diagnostics**: Live inspection of ADC pin voltages, divider ratios, and hardware bitmask.

## Planned Technology Stack
- **Framework**: React 18+ with Vite & TypeScript
- **Styling**: Tailwind CSS + shadcn/ui components
- **Charting**: Recharts or Chart.js
- **State & Data Fetching**: TanStack React Query (polling `/api/v1/sensors/latest` and `/api/v1/health`)
- **API Client**: Axios or standard Fetch API consuming FastAPI endpoints on port 8000.

## Endpoint Contract Prepared in Phase 1
- `GET /api/v1/sensors/latest` — Real-time sensor measurements & voltages
- `GET /api/v1/sensors/history?limit=100` — Time-series historical data
- `GET /api/v1/sensors/statistics` — Aggregate summary stats
- `GET /api/v1/health` — Hardware health & electrical safety state
- `GET /api/v1/alerts/summary` — Active warnings & critical alerts
- `POST /api/v1/chatbot/query` — AI advisor chat interface
