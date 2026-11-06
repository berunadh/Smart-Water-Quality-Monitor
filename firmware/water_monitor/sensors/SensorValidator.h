#pragma once

#include "SensorBase.h"
#include "../config.h"

/**
 * ============================================================================
 * SENSOR VALIDATOR & HEALTH AGGREGATOR
 * ============================================================================
 * Analyzes multi-sensor readings, verifies electrical safety invariants,
 * determines system-level alert severity, generates human-readable alert
 * banners, and compiles the 16-bit System Health bitmask for ThingSpeak Field 7.
 * ============================================================================
 */

class SensorValidator {
public:
    SensorValidator() 
        : _severity(SEVERITY_NORMAL),
          _healthCode(HEALTH_OK) {
        _activeAlertMessage[0] = '\0';
    }

    void evaluate(const SensorReading& ph, const SensorReading& turb, const SensorReading& tds, bool wifiConnected, bool cloudOk) {
        _healthCode = HEALTH_OK;
        _severity = SEVERITY_NORMAL;
        _activeAlertMessage[0] = '\0';

        // 1. Evaluate Network and Cloud Health
        if (!wifiConnected) {
            _healthCode |= HEALTH_WIFI_DISCONNECTED;
        }
        if (!cloudOk) {
            _healthCode |= HEALTH_CLOUD_ERROR;
        }

        // 2. Evaluate TDS Availability
        if (!tds.isValid || tds.status == STATUS_UNAVAILABLE) {
            _healthCode |= HEALTH_TDS_UNAVAILABLE;
        }

        // 3. Demo Mode Flag
        if (FEATURE_DEMO_MODE) {
            _healthCode |= HEALTH_DEMO_MODE_ACTIVE;
        }

        // 4. Electrical Safety & Over-Range Checks (Highest Priority)
        if (ph.status == STATUS_OVER_RANGE || turb.status == STATUS_OVER_RANGE || tds.status == STATUS_OVER_RANGE) {
            _healthCode |= HEALTH_ADC_OVER_RANGE;
            _severity = SEVERITY_SENSOR_FAULT;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "ADC OVER-RANGE!");
            return;
        }

        // 5. Hardware Faults / Disconnected Probes
        bool hasSensorFault = false;
        if (ph.status == STATUS_DISCONNECTED || ph.status == STATUS_STUCK || ph.status == STATUS_ERROR) {
            _healthCode |= HEALTH_PH_FAULT;
            hasSensorFault = true;
        }
        if (turb.status == STATUS_DISCONNECTED || turb.status == STATUS_STUCK || turb.status == STATUS_ERROR) {
            _healthCode |= HEALTH_TURB_FAULT;
            hasSensorFault = true;
        }

        if (hasSensorFault) {
            _severity = SEVERITY_SENSOR_FAULT;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "SENSOR ERROR");
            return;
        }

        // 6. Calibration Pending Flags
        if (ph.status == STATUS_CALIBRATION_PENDING || turb.status == STATUS_CALIBRATION_PENDING) {
            _healthCode |= HEALTH_CALIBRATION_PENDING;
        }

        // 7. Water Quality Critical Alerts
        if (turb.status == STATUS_CRITICAL) {
            _severity = SEVERITY_CRITICAL;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "HIGH TURBIDITY");
            return;
        }
        if (ph.status == STATUS_CRITICAL) {
            _severity = SEVERITY_CRITICAL;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "pH OUT OF RANGE");
            return;
        }

        // 8. Water Quality Warning Alerts
        if (turb.status == STATUS_WARNING && ph.status == STATUS_WARNING) {
            _severity = SEVERITY_WARNING;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "WATER QUALITY WARNING");
            return;
        }
        if (turb.status == STATUS_WARNING) {
            _severity = SEVERITY_WARNING;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "ELEVATED TURBIDITY");
            return;
        }
        if (ph.status == STATUS_WARNING) {
            _severity = SEVERITY_WARNING;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "pH OUT OF RANGE");
            return;
        }

        // 9. All conditions Normal
        _severity = SEVERITY_NORMAL;
        snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "WATER SYSTEM NORMAL");
    }

    AlertSeverity getSeverity() const {
        return _severity;
    }

    uint16_t getHealthCode() const {
        return _healthCode;
    }

    const char* getAlertMessage() const {
        return _activeAlertMessage;
    }

    const char* getSeverityName() const {
        switch (_severity) {
            case SEVERITY_NORMAL:       return "NORMAL";
            case SEVERITY_WARNING:      return "WARNING";
            case SEVERITY_CRITICAL:     return "CRITICAL";
            case SEVERITY_SENSOR_FAULT: return "FAULT";
            default:                    return "UNKNOWN";
        }
    }

private:
    AlertSeverity _severity;
    uint16_t _healthCode;
    char _activeAlertMessage[32];
};
