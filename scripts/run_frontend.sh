#!/usr/bin/env bash
set -e

# ==============================================================================
# Smart Apartment Water Quality Monitor — Frontend Launcher
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Starting HydroSense React Frontend ==="
cd "${PROJECT_ROOT}/frontend"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "[+] node_modules not found. Running npm install..."
    npm install --legacy-peer-deps --cache /tmp/npm-cache
fi

echo "[✓] Launching Vite development server on http://localhost:5173"
exec npm run dev -- --host 127.0.0.1 --port 5173
