#pragma once

#include <WiFi.h>
#include <HTTPClient.h>
#include "../config.h"
#include "../secrets.h"
#include "../sensors/SensorBase.h"
#include "../sensors/SensorValidator.h"

/**
 * ============================================================================
 * CLOUD MANAGER (THINGSPEAK & WI-FI INTEGRATION)
 * ============================================================================
 * Prepares the ESP32 firmware for ThingSpeak telemetry ingestion in Phase 2.
 * 
 * FIELD MAPPINGS:
 * - Field 1: Calibrated pH (omitted if uncalibrated or in error)
 * - Field 2: Calibrated Turbidity (NTU, omitted if uncalibrated or in error)
 * - Field 3: TDS (ppm, omitted / blank until sensor is installed. NEVER 0)
 * - Field 4: Alert Severity (0 = Normal, 1 = Warning, 2 = Critical, 3 = Fault)
 * - Field 5: pH Board Output Voltage (V_sensor = V_ADC * 2.50)
 * - Field 6: Turbidity Board Output Voltage (V_sensor = V_ADC * 2.50)
 * - Field 7: System Health Bitmask (16-bit integer)
 * 
 * Robustness:
 * Non-blocking Wi-Fi reconnect and HTTP client. If connection fails or drops,
 * local sensor monitoring and buzzer alerting continue without interruption.
 * ============================================================================
 */

class CloudManager {
public:
    CloudManager()
        : _lastUploadMillis(0),
          _lastWifiCheckMillis(0),
          _lastHttpStatus(0),
          _uploadCount(0),
          _failedUploads(0),
          _cloudStatusText("INIT") {}

    void begin() {
        if (String(WIFI_SSID) == "REPLACE_WITH_YOUR_SSID" || String(WIFI_SSID) == "YOUR_WIFI_SSID") {
            Serial.println(F("[WIFI] Warning: Default placeholder SSID detected. Wi-Fi inactive."));
            _cloudStatusText = "NO_CFG";
            return;
        }

        Serial.printf("[WIFI] Initiating connection to SSID: %s\n", WIFI_SSID);
        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        _cloudStatusText = "CONN";
    }

    bool isWifiConnected() const {
        return (WiFi.status() == WL_CONNECTED);
    }

    const char* getStatusText() const {
        return _cloudStatusText;
    }

    void update(uint32_t currentMillis,
                const SensorReading& ph,
                const SensorReading& turb,
                const SensorReading& tds,
                const SensorValidator& validator) {
        // 1. Maintain Wi-Fi Connection (Checked every 5 seconds)
        if (currentMillis - _lastWifiCheckMillis >= 5000) {
            _lastWifiCheckMillis = currentMillis;

            if (String(WIFI_SSID) == "REPLACE_WITH_YOUR_SSID" || String(WIFI_SSID) == "YOUR_WIFI_SSID") {
                _cloudStatusText = "NO_CFG";
                return;
            }

            if (WiFi.status() != WL_CONNECTED) {
                _cloudStatusText = "OFF";
                // Non-blocking reconnect attempt if disconnected
                static uint32_t lastReconnectAttempt = 0;
                if (currentMillis - lastReconnectAttempt >= 10000) {
                    lastReconnectAttempt = currentMillis;
                    Serial.println(F("[WIFI] Disconnected. Reconnecting..."));
                    WiFi.disconnect();
                    WiFi.reconnect();
                }
                return;
            } else {
                if (strcmp(_cloudStatusText, "OFF") == 0 || strcmp(_cloudStatusText, "CONN") == 0) {
                    _cloudStatusText = "IDLE";
                    Serial.printf("[WIFI] Connected! IP: %s | RSSI: %d dBm\n", 
                                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
                }
            }
        }

        // 2. Check ThingSpeak upload interval (20 seconds >= 15s rate limit)
        if (currentMillis - _lastUploadMillis < THINGSPEAK_INTERVAL_MS) {
            return;
        }

        if (WiFi.status() != WL_CONNECTED) {
            return;
        }

        _lastUploadMillis = currentMillis;

        // Verify valid API key before attempting upload
        if (String(THINGSPEAK_WRITE_API_KEY) == "REPLACE_WITH_WRITE_KEY" || 
            String(THINGSPEAK_WRITE_API_KEY) == "YOUR_THINGSPEAK_WRITE_KEY") {
            _cloudStatusText = "NO_KEY";
            Serial.println(F("[CLOUD] ThingSpeak Write API key not configured in secrets.h. Skipping upload."));
            return;
        }

        // 3. Construct Payload with strict contract rules
        // Field 1: pH (omitted if uncalibrated/invalid)
        // Field 2: Turbidity (omitted if uncalibrated/invalid)
        // Field 3: TDS (omitted if unavailable, NEVER 0)
        // Field 4: Alert Severity (0, 1, 2, 3)
        // Field 5: pH Reconstructed Voltage
        // Field 6: Turbidity Reconstructed Voltage
        // Field 7: System Health Bitmask

        String postData = "api_key=" + String(THINGSPEAK_WRITE_API_KEY);

        // Field 1: Calibrated pH
        if (ph.isValid && !isnan(ph.calibratedValue)) {
            postData += "&field1=" + String(ph.calibratedValue, 2);
        }

        // Field 2: Calibrated Turbidity
        if (turb.isValid && !isnan(turb.calibratedValue)) {
            postData += "&field2=" + String(turb.calibratedValue, 1);
        }

        // Field 3: TDS (Omitted if sensor not installed; STRICT: never upload 0)
        if (tds.isValid && !isnan(tds.calibratedValue) && tds.status != STATUS_UNAVAILABLE) {
            postData += "&field3=" + String(tds.calibratedValue, 0);
        }

        // Field 4: Severity code
        postData += "&field4=" + String((int)validator.getSeverity());

        // Field 5: pH signal board voltage (uncalibrated diagnostic)
        postData += "&field5=" + String(ph.reconstructedVoltage, 3);

        // Field 6: Turbidity signal board voltage (uncalibrated diagnostic)
        postData += "&field6=" + String(turb.reconstructedVoltage, 3);

        // Field 7: System Health Bitmask
        postData += "&field7=" + String(validator.getHealthCode());

        // 4. Transmit HTTP POST to ThingSpeak
        HTTPClient http;
        http.begin("http://api.thingspeak.com/update");
        http.addHeader("Content-Type", "application/x-www-form-urlencoded");
        http.setTimeout(4000); // 4-second timeout to prevent blocking

        _cloudStatusText = "TX...";
        int httpResponseCode = http.POST(postData);
        _lastHttpStatus = httpResponseCode;

        if (httpResponseCode > 0) {
            String response = http.getString();
            // ThingSpeak returns the newly created entry_id on success (>0), or 0 on rate limit
            long entryId = response.toInt();
            if (entryId > 0) {
                _uploadCount++;
                _cloudStatusText = "SYNC";
                Serial.printf("[CLOUD] ThingSpeak upload successful! Entry ID: %ld (Total: %lu)\n", 
                              entryId, _uploadCount);
            } else {
                _failedUploads++;
                _cloudStatusText = "RATE";
                Serial.printf("[CLOUD] ThingSpeak rate limit or rejected. Response: %s\n", response.c_str());
            }
        } else {
            _failedUploads++;
            _cloudStatusText = "ERR";
            Serial.printf("[CLOUD] HTTP POST failed, error: %s\n", http.errorToString(httpResponseCode).c_str());
        }

        http.end();
    }

private:
    uint32_t _lastUploadMillis;
    uint32_t _lastWifiCheckMillis;
    int _lastHttpStatus;
    uint32_t _uploadCount;
    uint32_t _failedUploads;
    const char* _cloudStatusText;
};
