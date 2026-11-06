# ThingSpeak Cloud Setup & Integration Guide

This guide walks you through creating and configuring your free **ThingSpeak** account, creating the telemetry channel, mapping all seven data fields, and configuring API keys for both the ESP32 firmware and the Python FastAPI backend.

---

## 1. Create a ThingSpeak Account

1. Navigate to [https://thingspeak.com](https://thingspeak.com) in your web browser.
2. Click **Get Started for Free** or **Sign Up**.
3. Create a MathWorks account (or log in with an existing account).
4. Verify your email address and accept the terms of service.

---

## 2. Create the Water Quality Channel

1. Once logged into ThingSpeak, click on **Channels** in the top navigation bar, then click **My Channels**.
2. Click the green **New Channel** button.
3. Fill in the channel settings:
   - **Name**: `Smart Apartment Water Quality Monitor`
   - **Description**: `Full-stack IoT and AI water monitoring system with ESP32 edge telemetry and Python ML analysis.`
4. Enable the checkboxes for **Field 1** through **Field 7** and enter the exact labels below:
   - **Field 1**: `pH`
   - **Field 2**: `Turbidity (NTU)`
   - **Field 3**: `TDS (ppm)`
   - **Field 4**: `Alert Severity`
   - **Field 5**: `pH Output Voltage (V)`
   - **Field 6**: `Turbidity Output Voltage (V)`
   - **Field 7**: `System Health Bitmask`
5. *(Optional)*: Check **Make Public** if you wish to allow public read access, or leave it private.
6. Scroll to the bottom and click **Save Channel**.

---

## 3. Retrieve Your Credentials

Click on the **API Keys** tab inside your channel dashboard. You will see:

| Credential | Description | Where It Is Used |
| :--- | :--- | :--- |
| **Channel ID** | Numeric identifier at the top of the channel page (e.g. `2841029`) | Used in `backend/.env` |
| **Write API Key** | 16-character alphanumeric key (e.g. `ABC123XYZ4567890`) | Used in **ESP32 Firmware** (`secrets.h`) |
| **Read API Key** | 16-character alphanumeric key (e.g. `XYZ987ABC6543210`) | Used in **Python Backend** (`backend/.env`) |

---

## 4. Where to Paste Your Credentials

### A. ESP32 Firmware (Write API Key)
The ESP32 firmware sends HTTP POST updates to ThingSpeak. It only requires the **Write API Key**:

1. Open:
   ```bash
   firmware/water_monitor/secrets.h
   ```
2. Paste your credentials:
   ```cpp
   #define WIFI_SSID               "YourWiFiNetworkName"
   #define WIFI_PASSWORD           "YourWiFiPassword"
   #define THINGSPEAK_CHANNEL_ID   2841029UL                     // Your Channel ID
   #define THINGSPEAK_WRITE_API_KEY "YOUR_16_CHAR_WRITE_KEY"     // <--- PASTE WRITE KEY HERE
   ```

### B. Python Backend (Read API Key & Channel ID)
The Python backend polls and retrieves historical telemetry from ThingSpeak. It only requires the **Read API Key** and **Channel ID**:

1. Open:
   ```bash
   backend/.env
   ```
2. Configure:
   ```bash
   DATA_MODE=real
   THINGSPEAK_CHANNEL_ID=2841029                   # <--- PASTE CHANNEL ID HERE
   THINGSPEAK_READ_API_KEY=YOUR_16_CHAR_READ_KEY  # <--- PASTE READ KEY HERE
   POLL_INTERVAL_SECONDS=20
   ```

> [!IMPORTANT]
> **Security Separation**: The ESP32 is given only write permission. The frontend and mobile apps are never given API keys; they query the FastAPI backend securely.

---

## 5. How Missing & Null Fields Are Handled

ThingSpeak's REST API stores data as rows of comma-separated or JSON fields:
- **Missing TDS**: Because the TDS probe is not physically installed in Phase 1/Phase 2, the ESP32 firmware **omits `&field3=` entirely from the HTTP POST payload**. ThingSpeak stores this field as `null` (empty string `""`). The Python backend explicitly deserializes empty strings to `None` in Python and `null` in SQLite/JSON, **never** coercing missing TDS to `0.0 ppm`.
- **Uncalibrated Probes**: When pH or turbidity probes are uncalibrated, their physical measurement fields (`field1` and `field2`) are omitted from upload, while their diagnostic board voltages (`field5` and `field6`) are uploaded honestly.

---

## 6. ThingSpeak Free Plan Rate Limits

- The free plan permits at most **1 update every 15 seconds**.
- The ESP32 firmware is configured with `THINGSPEAK_INTERVAL_MS = 20000` (20 seconds), comfortably respecting the rate limit.
- If an update is attempted before 15 seconds elapses, ThingSpeak returns `0` (entry ID 0), which the firmware logs as `[CLOUD] ThingSpeak rejected upload (Rate limit or invalid key)` and sets the OLED status to `Cld: RATE`.
