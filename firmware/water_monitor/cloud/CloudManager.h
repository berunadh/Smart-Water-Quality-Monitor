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
 * Full Phase 2 ThingSpeak REST API Integration for ESP32.
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
 * ROBUSTNESS & NON-BLOCKING ISOLATION:
 * - Non-blocking Wi-Fi reconnect state machine.
 * - Non-blocking transmission interval (20s >= 15s free limit).
 * - Automatic retry with 5s backoff on network failure.
 * - Tracks last successful upload timestamp and entry ID.
 * - Independent execution: local sensor acquisition, OLED refresh,
 *   and buzzer alerts continue completely uninterrupted if cloud fails.
 * ============================================================================
 */

class CloudManager {
public:
    CloudManager()
        : _lastUploadMillis(0),
          _lastSuccessMillis(0),
          _lastWifiCheckMillis(0),
          _lastHttpStatus(0),
          _lastEntryId(0),
          _uploadCount(0),
          _failedUploads(0),
          _retryPending(false),
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

    uint32_t getLastSuccessMillis() const {
        return _lastSuccessMillis;
    }

    long getLastEntryId() const {
        return _lastEntryId;
    }

    uint32_t getSecondsSinceLastUpload(uint32_t currentMillis) const {
        if (_lastSuccessMillis == 0) return 9999;
        return (currentMillis - _lastSuccessMillis) / 1000;
    }

    void update(uint32_t currentMillis,
                const SensorReading& ph,
                const SensorReading& turb,
                const SensorReading& tds,
                const SensorValidator& validator) {
        // 1. Maintain Wi-Fi Connection State (Non-blocking check every 5 seconds)
        if (currentMillis - _lastWifiCheckMillis >= 5000) {
            _lastWifiCheckMillis = currentMillis;

            if (String(WIFI_SSID) == "REPLACE_WITH_YOUR_SSID" || String(WIFI_SSID) == "YOUR_WIFI_SSID") {
                _cloudStatusText = "NO_CFG";
                return;
            }

            if (WiFi.status() != WL_CONNECTED) {
                _cloudStatusText = "OFF";
                // Attempt non-blocking reconnect every 10s if disconnected
                static uint32_t lastReconnectAttempt = 0;
                if (currentMillis - lastReconnectAttempt >= 10000) {
                    lastReconnectAttempt = currentMillis;
                    Serial.println(F("[WIFI] Disconnected. Reconnecting in background..."));
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

        // 2. Timing Gate: Determine if it is time to upload
        // If a retry is pending, wait 5s backoff; otherwise enforce THINGSPEAK_INTERVAL_MS (20s)
        uint32_t requiredInterval = _retryPending ? 5000 : THINGSPEAK_INTERVAL_MS;
        if (currentMillis - _lastUploadMillis < requiredInterval) {
            return;
        }

        if (WiFi.status() != WL_CONNECTED) {
            return;
        }

        _lastUploadMillis = currentMillis;

        // Verify that Write API key is configured
        if (String(THINGSPEAK_WRITE_API_KEY) == "REPLACE_WITH_WRITE_KEY" || 
            String(THINGSPEAK_WRITE_API_KEY) == "YOUR_THINGSPEAK_WRITE_KEY") {
            _cloudStatusText = "NO_KEY";
            Serial.println(F("[CLOUD] ThingSpeak Write API key not configured in secrets.h. Skipping upload."));
            return;
        }

        // 3. Construct Payload with strict contract rules
        String postData = "api_key=" + String(THINGSPEAK_WRITE_API_KEY);

        // Field 1: Calibrated pH (omitted if uncalibrated or in error)
        if (ph.isValid && !isnan(ph.calibratedValue)) {
            postData += "&field1=" + String(ph.calibratedValue, 2);
        }

        // Field 2: Calibrated Turbidity (omitted if uncalibrated or in error)
        if (turb.isValid && !isnan(turb.calibratedValue)) {
            postData += "&field2=" + String(turb.calibratedValue, 1);
        }

        // Field 3: TDS (STRICT REQUIREMENT: Omitted / blank when uninstalled. NEVER send 0)
        if (tds.isValid && !isnan(tds.calibratedValue) && tds.status != STATUS_UNAVAILABLE) {
            postData += "&field3=" + String(tds.calibratedValue, 0);
        }

        // Field 4: Alert Severity code (0=Normal, 1=Warning, 2=Critical, 3=Fault)
        postData += "&field4=" + String((int)validator.getSeverity());

        // Field 5: pH signal board voltage (uncalibrated diagnostic)
        postData += "&field5=" + String(ph.reconstructedVoltage, 3);

        // Field 6: Turbidity signal board voltage (uncalibrated diagnostic)
        postData += "&field6=" + String(turb.reconstructedVoltage, 3);

        // Field 7: System Health Bitmask (16-bit integer)
        postData += "&field7=" + String(validator.getHealthCode());

        // 4. Transmit HTTP POST to ThingSpeak API
        HTTPClient http;
        http.begin("http://api.thingspeak.com/update");
        http.addHeader("Content-Type", "application/x-www-form-urlencoded");
        http.setTimeout(3500); // 3.5s timeout prevents blocking sensor loop

        _cloudStatusText = "TX...";
        int httpResponseCode = http.POST(postData);
        _lastHttpStatus = httpResponseCode;

        if (httpResponseCode > 0) {
            String response = http.getString();
            long entryId = response.toInt();
            if (entryId > 0) {
                // Successful update returns positive entry_id
                _uploadCount++;
                _lastEntryId = entryId;
                _lastSuccessMillis = currentMillis;
                _retryPending = false;
                _cloudStatusText = "SYNC";
                Serial.printf("[CLOUD] ThingSpeak upload SUCCESS! Entry #%ld (Total: %lu)\n", 
                              entryId, _uploadCount);
            } else {
                // Return of "0" means rate limit (too frequent) or invalid API key
                _failedUploads++;
                _retryPending = false;
                _cloudStatusText = "RATE";
                Serial.printf("[CLOUD] ThingSpeak rejected upload (Rate limit or invalid key). Response: %s\n", response.c_str());
            }
        } else {
            // Network failure or timeout
            _failedUploads++;
            _cloudStatusText = "RETRY";
            _retryPending = true;
            Serial.printf("[CLOUD] HTTP POST failed: %s (will retry in 5s)\n", 
                          http.errorToString(httpResponseCode).c_str());
        }

        http.end();
    }

private:
    uint32_t _lastUploadMillis;
    uint32_t _lastSuccessMillis;
    uint32_t _lastWifiCheckMillis;
    int _lastHttpStatus;
    long _lastEntryId;
    uint32_t _uploadCount;
    uint32_t _failedUploads;
    bool _retryPending;
    const char* _cloudStatusText;
};
