#!/usr/bin/env bash
# ==============================================================================
# SMART WATER QUALITY MONITOR — FIRMWARE VERIFICATION SCRIPT (macOS)
# ==============================================================================
# Automatically locates the bundled Arduino CLI in Arduino IDE.app
# and compiles the water_monitor sketch against the ESP32 Dev Module target.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKETCH_DIR="${PROJECT_ROOT}/firmware/water_monitor"

echo "=== Smart Water Quality Monitor: ESP32 Firmware Build Check ==="

# 1. Locate arduino-cli
ARDUINO_CLI=""
if command -v arduino-cli >/dev/null 2>&1; then
    ARDUINO_CLI="arduino-cli"
elif [ -f "/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" ]; then
    ARDUINO_CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"
fi

if [ -z "${ARDUINO_CLI}" ]; then
    echo "[-] ERROR: arduino-cli executable not found."
    echo "    Please install arduino-cli or Arduino IDE 2.x into /Applications."
    exit 1
fi

echo "[+] Using Arduino CLI: ${ARDUINO_CLI}"
"${ARDUINO_CLI}" version

# 2. Check for secrets.h; if missing, create from secrets.example.h
if [ ! -f "${SKETCH_DIR}/secrets.h" ]; then
    echo "[!] secrets.h not found. Creating from secrets.example.h for build verification..."
    cp "${SKETCH_DIR}/secrets.example.h" "${SKETCH_DIR}/secrets.h"
fi

# 3. Compile sketch
echo "[+] Compiling sketch in ${SKETCH_DIR} for FQBN: esp32:esp32:esp32..."
"${ARDUINO_CLI}" compile --fqbn esp32:esp32:esp32 "${SKETCH_DIR}"

echo "[✓] BUILD SUCCESSFUL! Firmware compiles cleanly with 0 errors."
