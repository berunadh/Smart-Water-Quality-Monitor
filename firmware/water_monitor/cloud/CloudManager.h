#pragma once

#include <WiFi.h>
#include <HTTPClient.h>
#include "../config.h"

// Resilient inclusion of secrets.h (resolves in both Arduino IDE and command-line builds)
#if __has_include("../secrets.h")
    #include "../secrets.h"
#elif __has_include("secrets.h")
    #include "secrets.h"
#endif

#include "../sensors/SensorBase.h"
#include "../sensors/SensorValidator.h"

// Fallback declarations if macros are omitted from secrets.h
#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

#ifndef THINGSPEAK_CHANNEL_ID
#define THINGSPEAK_CHANNEL_ID 0UL
#endif

#ifndef THINGSPEAK_WRITE_API_KEY
#define THINGSPEAK_WRITE_API_KEY ""
#endif

/**
 * ============================================================================
 * CLOUD MANAGER (THINGSPEAK & WI-FI INTEGRATION)
 * ============================================================================
 * High-reliability network manager and telemetry transmitter for ESP32.
 * 
 * Formal Network Status States:
 * - NO_CFG                  : Wi-Fi credentials missing or placeholder
 * - WIFI_CONNECTING         : Currently associating with Wi-Fi AP
 * - WIFI_FAILED             : Wi-Fi connection timed out or failed
 * - WIFI_CONNECTED          : Connected to Wi-Fi AP, awaiting upload schedule
 * - THINGSPEAK_CONFIG_INVALID: Channel ID or Write Key missing or invalid
 * - THINGSPEAK_UPLOAD_SUCCESS: HTTP POST to ThingSpeak accepted (entry_id > 0)
 * - THINGSPEAK_UPLOAD_FAILED : HTTP error or rejected (response 0 / rate limit)
 * 
 * FIELD MAPPINGS:
 * - Field 1: Calibrated pH (omitted if uncalibrated or in error)
 * - Field 2: Calibrated Turbidity (NTU, omitted if uncalibrated or in error)
 * - Field 3: TDS (ppm, strictly omitted unless calibrated, valid & immersed. NEVER 0 or raw V)
 * - Field 4: Alert Severity (0 = Normal, 1 = Warning, 2 = Critical, 3 = Fault)
 * - Field 5: pH Board Output Voltage (V_sensor = V_ADC * 2.50)
 * - Field 6: Turbidity Board Output Voltage (V_sensor = V_ADC * 2.50)
 * - Field 7: System Health Bitmask (16-bit integer)
 * - Field 8: Optional TDS Direct ADC Voltage on GPIO35 (1.0x, diagnostic only)
 * ============================================================================
 */

class CloudManager {
public:
    static constexpr const char* STATUS_NO_CFG                   = "NO_CFG";
    static constexpr const char* STATUS_WIFI_CONNECTING          = "WIFI_CONNECTING";
    static constexpr const char* STATUS_WIFI_FAILED              = "WIFI_FAILED";
    static constexpr const char* STATUS_WIFI_CONNECTED           = "WIFI_CONNECTED";
    static constexpr const char* STATUS_THINGSPEAK_CONFIG_INVALID = "THINGSPEAK_CONFIG_INVALID";
    static constexpr const char* STATUS_THINGSPEAK_UPLOAD_SUCCESS = "THINGSPEAK_UPLOAD_SUCCESS";
    static constexpr const char* STATUS_THINGSPEAK_UPLOAD_FAILED  = "THINGSPEAK_UPLOAD_FAILED";

    CloudManager()
        : _lastUploadMillis(0),
          _lastSuccessMillis(0),
          _lastWifiCheckMillis(0),
          _wifiConnectStartMillis(0),
          _lastReconnectAttemptMillis(0),
          _lastHttpStatus(0),
          _lastEntryId(0),
          _uploadCount(0),
          _failedUploads(0),
          _retryPending(false),
          _wifiWasConnected(false),
          _isWifiConfigValid(false),
          _isThingSpeakConfigValid(false),
          _cloudStatusText(STATUS_NO_CFG) {}

    void begin() {
        // 1. Validate Wi-Fi credentials
        _isWifiConfigValid = validateWifiCredentials();
        _isThingSpeakConfigValid = validateThingSpeakCredentials();

        Serial.println();
        Serial.println(F("=========================================================="));
        Serial.println(F(" [NETWORK] Wi-Fi & ThingSpeak Subsystem Initialization    "));
        Serial.println(F("=========================================================="));

        if (!_isWifiConfigValid) {
            _cloudStatusText = STATUS_NO_CFG;
            Serial.println(F("[WIFI] ERROR: Wi-Fi credentials missing or placeholder in secrets.h!"));
            Serial.println(F("[WIFI] Network state: NO_CFG. Physical sensor monitoring continues locally."));
            Serial.println(F("=========================================================="));
            return;
        }

        Serial.printf("[WIFI] Target SSID   : %s\n", WIFI_SSID);
        Serial.printf("[WIFI] Password      : [CONFIGURED - %d chars]\n", (int)strlen(WIFI_PASSWORD));

        if (_isThingSpeakConfigValid) {
            char maskedKey[32] = {0};
            size_t klen = strlen(THINGSPEAK_WRITE_API_KEY);
            if (klen >= 6) {
                snprintf(maskedKey, sizeof(maskedKey), "%.2s************%.2s", 
                         THINGSPEAK_WRITE_API_KEY, THINGSPEAK_WRITE_API_KEY + klen - 2);
            } else {
                snprintf(maskedKey, sizeof(maskedKey), "******");
            }
            Serial.printf("[CLOUD] Channel ID   : %lu\n", (unsigned long)THINGSPEAK_CHANNEL_ID);
            Serial.printf("[CLOUD] Write API Key: %s\n", maskedKey);
        } else {
            Serial.println(F("[CLOUD] WARNING: ThingSpeak credentials missing or invalid in secrets.h."));
            Serial.println(F("[CLOUD] Wi-Fi will connect, but cloud telemetry upload will be disabled."));
        }
        Serial.println(F("=========================================================="));

        // 2. Initiate non-blocking Wi-Fi connection
        WiFi.persistent(false);
        WiFi.disconnect(true);
        delay(100);
        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

        _wifiConnectStartMillis = millis();
        _lastReconnectAttemptMillis = _wifiConnectStartMillis;
        _cloudStatusText = STATUS_WIFI_CONNECTING;
        Serial.println(F("[WIFI] Initiating connection... Status: WIFI_CONNECTING"));
    }

    bool isWifiConnected() const {
        return (WiFi.status() == WL_CONNECTED);
    }

    bool isThingSpeakConfigValid() const {
        return _isThingSpeakConfigValid;
    }

    bool isCloudHealthy() const {
        if (!isWifiConnected() || !_isThingSpeakConfigValid) {
            return false;
        }
        if (strcmp(_cloudStatusText, STATUS_THINGSPEAK_UPLOAD_FAILED) == 0) {
            return false;
        }
        return true;
    }

    const char* getStatusText() const {
        return _cloudStatusText;
    }

    const char* getOledTag() const {
        if (strcmp(_cloudStatusText, STATUS_THINGSPEAK_UPLOAD_SUCCESS) == 0) return "SYNC";
        if (strcmp(_cloudStatusText, STATUS_WIFI_CONNECTED) == 0) return "OK";
        if (strcmp(_cloudStatusText, STATUS_WIFI_CONNECTING) == 0) return "CONN";
        if (strcmp(_cloudStatusText, STATUS_WIFI_FAILED) == 0) return "FAIL";
        if (strcmp(_cloudStatusText, STATUS_THINGSPEAK_UPLOAD_FAILED) == 0) return "ERR";
        if (strcmp(_cloudStatusText, STATUS_THINGSPEAK_CONFIG_INVALID) == 0) return "BAD_KEY";
        if (strcmp(_cloudStatusText, STATUS_NO_CFG) == 0) return "NO_CFG";
        return _cloudStatusText;
    }

    uint32_t getLastSuccessMillis() const {
        return _lastSuccessMillis;
    }

    long getLastEntryId() const {
        return _lastEntryId;
    }

    uint32_t getUploadCount() const {
        return _uploadCount;
    }

    uint32_t getFailedUploads() const {
        return _failedUploads;
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
        // --------------------------------------------------------------------
        // 1. Maintain Wi-Fi Connection State Machine (Checked every 1.0 second)
        // --------------------------------------------------------------------
        if (currentMillis - _lastWifiCheckMillis >= 1000) {
            _lastWifiCheckMillis = currentMillis;

            if (!_isWifiConfigValid) {
                _cloudStatusText = STATUS_NO_CFG;
                return;
            }

            if (WiFi.status() == WL_CONNECTED) {
                if (!_wifiWasConnected) {
                    _wifiWasConnected = true;
                    Serial.println();
                    Serial.println(F("----------------------------------------------------------"));
                    Serial.println(F("[WIFI] CONNECTED SUCCESSFULLY!                             "));
                    Serial.printf("[WIFI] IP Address : %s\n", WiFi.localIP().toString().c_str());
                    Serial.printf("[WIFI] Subnet Mask: %s\n", WiFi.subnetMask().toString().c_str());
                    Serial.printf("[WIFI] Gateway    : %s\n", WiFi.gatewayIP().toString().c_str());
                    Serial.printf("[WIFI] RSSI       : %d dBm\n", WiFi.RSSI());
                    Serial.println(F("----------------------------------------------------------"));

                    if (!_isThingSpeakConfigValid) {
                        _cloudStatusText = STATUS_THINGSPEAK_CONFIG_INVALID;
                    } else if (strcmp(_cloudStatusText, STATUS_THINGSPEAK_UPLOAD_SUCCESS) != 0) {
                        _cloudStatusText = STATUS_WIFI_CONNECTED;
                    }
                }
            } else {
                // Wi-Fi is NOT connected
                if (_wifiWasConnected) {
                    _wifiWasConnected = false;
                    _cloudStatusText = STATUS_WIFI_CONNECTING;
                    _wifiConnectStartMillis = currentMillis;
                    _lastReconnectAttemptMillis = currentMillis;
                    Serial.println(F("[WIFI] Connection lost! Reconnecting in background..."));
                    WiFi.disconnect();
                    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
                } else if (strcmp(_cloudStatusText, STATUS_WIFI_CONNECTING) == 0) {
                    // Check for connection timeout (25 seconds)
                    if (currentMillis - _wifiConnectStartMillis >= 25000) {
                        _cloudStatusText = STATUS_WIFI_FAILED;
                        _lastReconnectAttemptMillis = currentMillis;
                        Serial.println(F("[WIFI] Connection attempt timed out (25s). Status: WIFI_FAILED."));
                        Serial.println(F("[WIFI] Local monitoring continuing normally. Background retry in 20s."));
                    }
                } else if (strcmp(_cloudStatusText, STATUS_WIFI_FAILED) == 0) {
                    // Periodic non-blocking reconnect retry every 20 seconds
                    if (currentMillis - _lastReconnectAttemptMillis >= 20000) {
                        _lastReconnectAttemptMillis = currentMillis;
                        _wifiConnectStartMillis = currentMillis;
                        _cloudStatusText = STATUS_WIFI_CONNECTING;
                        Serial.println(F("[WIFI] Retrying Wi-Fi association in background... Status: WIFI_CONNECTING"));
                        WiFi.disconnect();
                        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
                    }
                }
            }
        }

        // --------------------------------------------------------------------
        // 2. Validate Pre-Conditions for ThingSpeak Upload
        // --------------------------------------------------------------------
        if (!_isThingSpeakConfigValid) {
            if (WiFi.status() == WL_CONNECTED) {
                _cloudStatusText = STATUS_THINGSPEAK_CONFIG_INVALID;
            }
            return;
        }

        if (WiFi.status() != WL_CONNECTED) {
            return;
        }

        // --------------------------------------------------------------------
        // 3. Timing Gate (20-second minimum upload interval; 5s retry backoff)
        // --------------------------------------------------------------------
        uint32_t requiredInterval = _retryPending ? 5000 : THINGSPEAK_INTERVAL_MS;
        if (currentMillis - _lastUploadMillis < requiredInterval) {
            return;
        }

        _lastUploadMillis = currentMillis;

        // --------------------------------------------------------------------
        // 4. Construct Telemetry Payload (Strict Data Contract Rules)
        // --------------------------------------------------------------------
        String postData = "api_key=" + String(THINGSPEAK_WRITE_API_KEY);

        bool phHasVal = (ph.isValid && !isnan(ph.calibratedValue) && !isinf(ph.calibratedValue) &&
                         ph.status != STATUS_CALIBRATION_PENDING && ph.status != STATUS_OUT_OF_CAL_RANGE);
        bool turbHasVal = (turb.isValid && !isnan(turb.calibratedValue) && !isinf(turb.calibratedValue) &&
                           turb.status != STATUS_CALIBRATION_PENDING && turb.status != STATUS_OUT_OF_CAL_RANGE);
        bool tdsHasVal = (FEATURE_TDS_ENABLED && tds.isValid && !isnan(tds.calibratedValue) && !isinf(tds.calibratedValue) &&
                          tds.status != STATUS_CALIBRATION_PENDING && tds.status != STATUS_DRY_OR_NOT_IMMERSED &&
                          tds.status != STATUS_DISCONNECTED && tds.status != STATUS_OVER_RANGE &&
                          tds.status != STATUS_STUCK && tds.status != STATUS_ERROR &&
                          tds.status != STATUS_UNAVAILABLE);

#if THINGSPEAK_USE_5FIELD_PROFILE
        // Documented 5-Field Profile (Design Doc Channel 3448045 compatible layout):
        // field1=TDS ppm, field2=pH, field3=Turbidity NTU, field4=Custom WQS, field5=System status code
        if (tdsHasVal) {
            postData += "&field1=" + String(tds.calibratedValue, 0);
        }
        if (phHasVal) {
            postData += "&field2=" + String(ph.calibratedValue, 2);
        }
        if (turbHasVal) {
            postData += "&field3=" + String(turb.calibratedValue, 1);
        }
        if (validator.isWqsValid() && !isnan(validator.getWqs()) && !isinf(validator.getWqs())) {
            postData += "&field4=" + String(validator.getWqs(), 1);
        }
        postData += "&field5=" + String(validator.getWaterStatusCode());
#else
        // Existing Project 8-Field Mapping (Channel ID 3570138):
        // Field 1: Calibrated pH (omitted if uncalibrated, out-of-range, or in error)
        if (phHasVal) {
            postData += "&field1=" + String(ph.calibratedValue, 2);
        }

        // Field 2: Calibrated Turbidity (strictly omitted if uncalibrated, out-of-range, or in error)
        if (turbHasVal) {
            postData += "&field2=" + String(turb.calibratedValue, 1);
        }

        // Field 3: TDS ppm (uploaded for valid/critical liquid readings; omitted when dry/fault/uncalibrated)
        if (tdsHasVal) {
            postData += "&field3=" + String(tds.calibratedValue, 0);
        }

        // Field 4: Alert Severity code (0=Normal, 1=Warning, 2=Critical, 3=Fault)
        postData += "&field4=" + String((int)validator.getSeverity());

        // Field 5: pH signal board reconstructed voltage (2.5x)
        if (!isnan(ph.reconstructedVoltage) && !isinf(ph.reconstructedVoltage) && ph.reconstructedVoltage >= 0.0f) {
            postData += "&field5=" + String(ph.reconstructedVoltage, 3);
        }

        // Field 6: Turbidity signal board reconstructed voltage (2.5x)
        if (!isnan(turb.reconstructedVoltage) && !isinf(turb.reconstructedVoltage) && turb.reconstructedVoltage >= 0.0f) {
            postData += "&field6=" + String(turb.reconstructedVoltage, 3);
        }

        // Field 7: System Health Bitmask (16-bit integer)
        postData += "&field7=" + String(validator.getHealthCode());

        // Field 8 (Optional Diagnostic): TDS direct ADC voltage (GPIO35, 1.0x)
        if (FEATURE_TDS_ENABLED && !isnan(tds.adcVoltage) && !isinf(tds.adcVoltage) && tds.adcVoltage >= 0.0f) {
            postData += "&field8=" + String(tds.adcVoltage, 3);
        }
#endif

        // --------------------------------------------------------------------
        // 5. Transmit HTTP POST to ThingSpeak API
        // --------------------------------------------------------------------
        HTTPClient http;
        http.begin("http://api.thingspeak.com/update");
        http.addHeader("Content-Type", "application/x-www-form-urlencoded");
        http.setTimeout(3500); // 3.5s timeout prevents blocking sensor loop

        int httpResponseCode = http.POST(postData);
        _lastHttpStatus = httpResponseCode;

        if (httpResponseCode > 0) {
            String response = http.getString();
            response.trim();
            long entryId = response.toInt();

            if (entryId > 0) {
                _uploadCount++;
                _lastEntryId = entryId;
                _lastSuccessMillis = currentMillis;
                _retryPending = false;
                _cloudStatusText = STATUS_THINGSPEAK_UPLOAD_SUCCESS;

                Serial.printf("[CLOUD] ThingSpeak upload SUCCESS! Entry #%ld (Total: %lu | Health: 0x%04X)\n", 
                              entryId, _uploadCount, validator.getHealthCode());
            } else {
                _failedUploads++;
                _retryPending = false;
                _cloudStatusText = STATUS_THINGSPEAK_UPLOAD_FAILED;

                Serial.printf("[CLOUD] ThingSpeak upload REJECTED (Response: '%s'). Rate-limit (<15s) or API key invalid.\n", 
                              response.c_str());
            }
        } else {
            _failedUploads++;
            _retryPending = true;
            _cloudStatusText = STATUS_THINGSPEAK_UPLOAD_FAILED;

            Serial.printf("[CLOUD] HTTP POST failed: %s (code %d). Retrying in 5s.\n", 
                          http.errorToString(httpResponseCode).c_str(), httpResponseCode);
        }

        http.end();
    }

    void printNetworkDiagnostics() const {
        Serial.println();
        Serial.println(F("==================== NETWORK & CLOUD DIAGNOSTICS ===================="));
        Serial.printf("Network Status             : %s\n", _cloudStatusText);
        Serial.printf("Wi-Fi Associated           : %s\n", isWifiConnected() ? "YES" : "NO");
        Serial.printf("Configured SSID            : %s\n", WIFI_SSID);
        if (isWifiConnected()) {
            Serial.printf("IP Address                 : %s\n", WiFi.localIP().toString().c_str());
            Serial.printf("Signal Strength (RSSI)     : %d dBm\n", WiFi.RSSI());
        }
        Serial.printf("ThingSpeak Config Valid    : %s\n", _isThingSpeakConfigValid ? "YES" : "NO (Check secrets.h)");
        Serial.printf("ThingSpeak Channel ID      : %lu\n", (unsigned long)THINGSPEAK_CHANNEL_ID);
        Serial.printf("ThingSpeak Field Profile   : %s\n", THINGSPEAK_USE_5FIELD_PROFILE ? "5-FIELD (Documented)" : "8-FIELD (Default)");
        Serial.printf("Successful Cloud Uploads   : %lu\n", _uploadCount);
        Serial.printf("Failed Cloud Uploads       : %lu\n", _failedUploads);
        Serial.printf("Last Upload Entry ID       : %ld\n", _lastEntryId);
        if (_lastSuccessMillis > 0) {
            Serial.printf("Seconds Since Last Upload  : %lu s\n", (millis() - _lastSuccessMillis) / 1000);
        } else {
            Serial.println(F("Seconds Since Last Upload  : None yet"));
        }
        Serial.println(F("====================================================================="));
        Serial.println();
    }

private:
    uint32_t _lastUploadMillis;
    uint32_t _lastSuccessMillis;
    uint32_t _lastWifiCheckMillis;
    uint32_t _wifiConnectStartMillis;
    uint32_t _lastReconnectAttemptMillis;
    int _lastHttpStatus;
    long _lastEntryId;
    uint32_t _uploadCount;
    uint32_t _failedUploads;
    bool _retryPending;
    bool _wifiWasConnected;
    bool _isWifiConfigValid;
    bool _isThingSpeakConfigValid;
    const char* _cloudStatusText;

    bool validateWifiCredentials() const {
        const char* ssid = WIFI_SSID;
        if (!ssid || strlen(ssid) == 0) return false;

        // Check common template placeholders
        if (strcmp(ssid, "YOUR_WIFI_SSID") == 0 ||
            strcmp(ssid, "REPLACE_WITH_YOUR_SSID") == 0 ||
            strcmp(ssid, "MY_WIFI_SSID") == 0 ||
            strcmp(ssid, "YOUR_SSID") == 0 ||
            strcmp(ssid, "SSID") == 0) {
            return false;
        }

        return true;
    }

    bool validateThingSpeakCredentials() const {
        if (THINGSPEAK_CHANNEL_ID == 0UL) {
            return false;
        }

        const char* key = THINGSPEAK_WRITE_API_KEY;
        if (!key || strlen(key) < 10) {
            return false;
        }

        // Check common template placeholders
        if (strcmp(key, "YOUR_THINGSPEAK_WRITE_KEY") == 0 ||
            strcmp(key, "REPLACE_WITH_WRITE_KEY") == 0 ||
            strcmp(key, "MY_THINGSPEAK_WRITE_API_KEY") == 0 ||
            strcmp(key, "YOUR_WRITE_KEY") == 0) {
            return false;
        }

        return true;
    }
};
