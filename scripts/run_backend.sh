#!/usr/bin/env bash
set -e

# ==============================================================================
# Smart Apartment Water Quality Monitor — Backend Launcher
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Starting HydroSense FastAPI Backend ==="
cd "${PROJECT_ROOT}/backend"

# Check if virtualenv exists, create if missing
if [ ! -d "venv" ]; then
    echo "[+] Virtualenv not found. Creating backend/venv..."
    python3 -m venv venv
    echo "[+] Installing backend dependencies..."
    ./venv/bin/pip install -r requirements.txt
fi

# Ensure .env exists
if [ ! -f ".env" ]; then
    echo "[!] .env not found. Copying .env.example to .env..."
    cp .env.example .env
fi

echo "[✓] Launching Uvicorn server on http://127.0.0.1:8000 (API docs: /docs)"
exec ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
