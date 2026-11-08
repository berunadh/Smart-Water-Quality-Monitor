#!/usr/bin/env bash
set -e

# ==============================================================================
# HydroSense: Smart Apartment Water Quality Monitor
# Single Command Full-Stack Launcher (Backend + Frontend)
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"

echo ""
echo "========================================================================"
echo "   💧 HydroSense: Smart Apartment Water Quality Monitor"
echo "   Full-Stack IoT, AI & ML Monitoring System"
echo "========================================================================"
echo ""

# Ensure backend venv exists
if [ ! -d "${BACKEND_DIR}/venv" ]; then
    echo "[+] Initializing Python virtual environment in backend/venv..."
    python3 -m venv "${BACKEND_DIR}/venv"
    echo "[+] Installing backend dependencies..."
    "${BACKEND_DIR}/venv/bin/pip" install -r "${BACKEND_DIR}/requirements.txt"
fi

# Ensure .env exists
if [ ! -f "${BACKEND_DIR}/.env" ]; then
    echo "[!] backend/.env not found. Creating from .env.example..."
    cp "${BACKEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
fi

# Ensure frontend dependencies exist
if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
    echo "[+] Installing frontend npm dependencies..."
    (cd "${FRONTEND_DIR}" && npm install --legacy-peer-deps --cache /tmp/npm-cache)
fi

echo "[1/2] Starting Python FastAPI Backend on http://127.0.0.1:8000..."
cd "${BACKEND_DIR}"
"${BACKEND_DIR}/venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

echo "[2/2] Starting React Vite Frontend on http://localhost:5173..."
cd "${FRONTEND_DIR}"
npm run dev -- --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!

# Trap Ctrl+C (SIGINT) and termination (SIGTERM) to kill both child processes cleanly
cleanup() {
    echo ""
    echo "[!] Shutting down HydroSense backend and frontend..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID 2>/dev/null || true
    wait $FRONTEND_PID 2>/dev/null || true
    echo "[✓] Both services stopped cleanly. Goodbye!"
    exit 0
}

trap cleanup INT TERM

echo ""
echo "========================================================================"
echo "   🚀 All Systems Live & Connected!"
echo "   - Web Dashboard:    http://localhost:5173"
echo "   - FastAPI REST API: http://127.0.0.1:8000/docs"
echo "   - Health Check:     http://127.0.0.1:8000/api/health"
echo "========================================================================"
echo "   Press [Ctrl + C] anytime to stop both servers."
echo "========================================================================"
echo ""

# Wait for both processes
wait
