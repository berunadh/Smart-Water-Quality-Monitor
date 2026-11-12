#pragma once

#include <Arduino.h>
#include <Preferences.h>
#include "SensorBase.h"
#include "WaterQualityScore.h"
#include "../config.h"

/**
 * ============================================================================
 * DUAL-MODE SENSOR VALIDATOR, THRESHOLD ENGINE & HEALTH AGGREGATOR
 * ============================================================================
 * Evaluates pH, Turbidity, and TDS independently against the active mode:
 * - MODE_DRINKING      (BIS IS 10500:2012 acceptable limits)
 * - MODE_REGULAR_USAGE (User-configurable non-drinking operational settings)
 * 
 * CRITICAL SAFETY & BUZZER RULES:
 * - Only valid, calibrated sensors with finite values are checked against limits.
 * - Uncalibrated, disconnected, or faulty sensors NEVER trigger threshold alarms
 *   and NEVER sound the acoustic buzzer.
 * - Hysteresis prevents rapid buzzer toggling when readings hover near thresholds.
 * - Tracks exact violated parameters so Serial, OLED, and logs identify the cause.
 * ============================================================================
 */

struct ModeThresholds {
    float phMin;
    float phMax;
    float phCritLow;
    float phCritHigh;
    float turbMax;
    float turbCritMax;
    float tdsMax;
    float tdsCritMax;
};

class SensorValidator {
public:
    SensorValidator() 
        : _mode(MODE_DRINKING),
          _severity(SEVERITY_NORMAL),
          _thresholdSeverity(SEVERITY_NORMAL),
          _healthCode(HEALTH_OK),
          _phViolated(false),
          _turbViolated(false),
          _tdsViolated(false) {
        memset(&_wqsResult, 0, sizeof(_wqsResult));
        _wqsResult.wqsValid = false;
        _wqsResult.wqs = NAN;
        _wqsResult.qPh = NAN;
        _wqsResult.qTds = NAN;
        _wqsResult.qTurb = NAN;
        _wqsResult.waterStatusCode = WATER_STATUS_FAULT;
        _activeAlertMessage[0] = '\0';
        resetToDefaults();
    }

    void begin() {
        loadSettings();
    }

    void resetToDefaults() {
        // BIS IS 10500:2012 Acceptable Limits (Drinking Mode)
        _drinkingThresholds = {
            DRINKING_PH_MIN,
            DRINKING_PH_MAX,
            DRINKING_PH_CRIT_MIN,
            DRINKING_PH_CRIT_MAX,
            DRINKING_TURB_MAX_NTU,
            DRINKING_TURB_CRIT_NTU,
            DRINKING_TDS_MAX_PPM,
            DRINKING_TDS_CRIT_PPM
        };

        // Provisional Configurable Non-Drinking Operational Defaults (Regular Usage Mode)
        _regularThresholds = {
            REGULAR_PH_MIN,
            REGULAR_PH_MAX,
            REGULAR_PH_CRIT_MIN,
            REGULAR_PH_CRIT_MAX,
            REGULAR_TURB_MAX_NTU,
            REGULAR_TURB_CRIT_NTU,
            REGULAR_TDS_MAX_PPM,
            REGULAR_TDS_CRIT_PPM
        };
    }

    WaterQualityMode getMode() const { return _mode; }
    const char* getModeName() const { return (_mode == MODE_DRINKING) ? "DRINKING" : "REGULAR_USAGE"; }
    const char* getModeShortTag() const { return (_mode == MODE_DRINKING) ? "DRK" : "REG"; }

    const ModeThresholds& getActiveThresholds() const {
        return (_mode == MODE_DRINKING) ? _drinkingThresholds : _regularThresholds;
    }

    const ModeThresholds& getDrinkingThresholds() const { return _drinkingThresholds; }
    const ModeThresholds& getRegularThresholds() const { return _regularThresholds; }

    void setMode(WaterQualityMode mode, bool persist = true) {
        _mode = mode;
        // Clear hysteresis latches on mode change so new limits evaluate cleanly
        _phViolated = false;
        _turbViolated = false;
        _tdsViolated = false;
        if (persist) {
            saveSettings();
        }
    }

    bool setRegularThresholds(float phMin, float phMax, float turbMax, float tdsMax, bool persist = true) {
        if (phMin < 0.0f || phMax > 14.0f || phMin >= phMax || turbMax <= 0.0f || tdsMax <= 0.0f) {
            return false;
        }
        _regularThresholds.phMin = phMin;
        _regularThresholds.phMax = phMax;
        _regularThresholds.phCritLow = max(0.0f, phMin - 1.0f);
        _regularThresholds.phCritHigh = min(14.0f, phMax + 1.0f);
        _regularThresholds.turbMax = turbMax;
        _regularThresholds.turbCritMax = turbMax * 2.5f;
        _regularThresholds.tdsMax = tdsMax;
        _regularThresholds.tdsCritMax = tdsMax * 2.0f;
        _phViolated = false;
        _turbViolated = false;
        _tdsViolated = false;
        if (persist) saveSettings();
        return true;
    }

    bool setDrinkingThresholds(float phMin, float phMax, float turbMax, float tdsMax, bool persist = true) {
        if (phMin < 0.0f || phMax > 14.0f || phMin >= phMax || turbMax <= 0.0f || tdsMax <= 0.0f) {
            return false;
        }
        _drinkingThresholds.phMin = phMin;
        _drinkingThresholds.phMax = phMax;
        _drinkingThresholds.phCritLow = max(0.0f, phMin - 1.0f);
        _drinkingThresholds.phCritHigh = min(14.0f, phMax + 1.0f);
        _drinkingThresholds.turbMax = turbMax;
        _drinkingThresholds.turbCritMax = max(5.0f, turbMax * 4.0f);
        _drinkingThresholds.tdsMax = tdsMax;
        _drinkingThresholds.tdsCritMax = tdsMax * 2.0f;
        _phViolated = false;
        _turbViolated = false;
        _tdsViolated = false;
        if (persist) saveSettings();
        return true;
    }

    void saveSettings() {
        Preferences prefs;
        if (prefs.begin("watersens", false)) {
            prefs.putUChar("wq_mode", (uint8_t)_mode);
            prefs.putFloat("dr_ph_min", _drinkingThresholds.phMin);
            prefs.putFloat("dr_ph_max", _drinkingThresholds.phMax);
            prefs.putFloat("dr_tb_max", _drinkingThresholds.turbMax);
            prefs.putFloat("dr_td_max", _drinkingThresholds.tdsMax);
            prefs.putFloat("rg_ph_min", _regularThresholds.phMin);
            prefs.putFloat("rg_ph_max", _regularThresholds.phMax);
            prefs.putFloat("rg_tb_max", _regularThresholds.turbMax);
            prefs.putFloat("rg_td_max", _regularThresholds.tdsMax);
            prefs.end();
        }
    }

    void loadSettings() {
        resetToDefaults();
        Preferences prefs;
        if (prefs.begin("watersens", true)) {
            uint8_t m = prefs.getUChar("wq_mode", (uint8_t)MODE_DRINKING);
            _mode = (m == (uint8_t)MODE_REGULAR_USAGE) ? MODE_REGULAR_USAGE : MODE_DRINKING;

            float drPhMin = prefs.getFloat("dr_ph_min", DRINKING_PH_MIN);
            float drPhMax = prefs.getFloat("dr_ph_max", DRINKING_PH_MAX);
            float drTbMax = prefs.getFloat("dr_tb_max", DRINKING_TURB_MAX_NTU);
            float drTdMax = prefs.getFloat("dr_td_max", DRINKING_TDS_MAX_PPM);
            if (drPhMin < drPhMax && drTbMax > 0.0f && drTdMax > 0.0f) {
                setDrinkingThresholds(drPhMin, drPhMax, drTbMax, drTdMax, false);
            }

            float rgPhMin = prefs.getFloat("rg_ph_min", REGULAR_PH_MIN);
            float rgPhMax = prefs.getFloat("rg_ph_max", REGULAR_PH_MAX);
            float rgTbMax = prefs.getFloat("rg_tb_max", REGULAR_TURB_MAX_NTU);
            float rgTdMax = prefs.getFloat("rg_td_max", REGULAR_TDS_MAX_PPM);
            if (rgPhMin < rgPhMax && rgTbMax > 0.0f && rgTdMax > 0.0f) {
                setRegularThresholds(rgPhMin, rgPhMax, rgTbMax, rgTdMax, false);
            }
            prefs.end();
        } else if (prefs.begin("watersens", false)) {
            // Initialize namespace non-destructively if missing on first boot
            prefs.end();
        }
        Serial.printf("[MODE] Active Water Quality Mode: %s (pH %.1f-%.1f | Turb <= %.1f NTU | TDS <= %.0f ppm)\n",
                      getModeName(),
                      getActiveThresholds().phMin,
                      getActiveThresholds().phMax,
                      getActiveThresholds().turbMax,
                      getActiveThresholds().tdsMax);
    }

    void evaluate(
        const SensorReading& ph,
        const SensorReading& turb,
        const SensorReading& tds,
        bool wifiConnected,
        bool cloudOk,
        bool tdsVerifiedCalibrated = true,
        bool phProvisional = false,
        bool turbProvisional = false
    ) {
        _healthCode = HEALTH_OK;
        _severity = SEVERITY_NORMAL;
        _thresholdSeverity = SEVERITY_NORMAL;
        _activeAlertMessage[0] = '\0';

        // 1. Network, Cloud, Mode, and Demo Flags
        if (!wifiConnected) _healthCode |= HEALTH_WIFI_DISCONNECTED;
        if (!cloudOk)       _healthCode |= HEALTH_CLOUD_ERROR;
        if (FEATURE_DEMO_MODE) _healthCode |= HEALTH_DEMO_MODE_ACTIVE;
        if (_mode == MODE_REGULAR_USAGE) _healthCode |= HEALTH_MODE_REGULAR;

        // 2. TDS Availability, Dry Probe, Provisional Model, & Hardware Fault Tracking
        if (tds.status == STATUS_UNAVAILABLE) {
            _healthCode |= HEALTH_TDS_UNAVAILABLE;
        }
        if (tds.status == STATUS_DRY_OR_NOT_IMMERSED) {
            _healthCode |= HEALTH_TDS_DRY;
        }
        if (tds.status == STATUS_DISCONNECTED || tds.status == STATUS_STUCK ||
            tds.status == STATUS_OVER_RANGE || tds.status == STATUS_ERROR) {
            _healthCode |= HEALTH_TDS_FAULT;
        }
        if (tds.isValid && !tdsVerifiedCalibrated &&
            tds.status != STATUS_UNAVAILABLE && tds.status != STATUS_CALIBRATION_PENDING) {
            _healthCode |= HEALTH_TDS_PROVISIONAL;
        }
        if (phProvisional && ph.status != STATUS_UNAVAILABLE) {
            _healthCode |= HEALTH_PH_PROVISIONAL;
        }
        if (turbProvisional && turb.status != STATUS_UNAVAILABLE) {
            _healthCode |= HEALTH_TURB_PROVISIONAL;
        }

        // 3. Electrical Safety & Over-Range Checks
        bool hasOverRange = (ph.status == STATUS_OVER_RANGE || turb.status == STATUS_OVER_RANGE || tds.status == STATUS_OVER_RANGE);
        if (hasOverRange) {
            _healthCode |= HEALTH_ADC_OVER_RANGE;
        }

        // 4. Genuine Hardware Faults / Disconnected Probes (distinct from Dry and Cal Pending!)
        bool hasSensorFault = false;
        if (ph.status == STATUS_DISCONNECTED || ph.status == STATUS_STUCK || ph.status == STATUS_ERROR || ph.status == STATUS_OVER_RANGE) {
            _healthCode |= HEALTH_PH_FAULT;
            hasSensorFault = true;
        }
        if (turb.status == STATUS_DISCONNECTED || turb.status == STATUS_STUCK || turb.status == STATUS_ERROR || turb.status == STATUS_OVER_RANGE) {
            _healthCode |= HEALTH_TURB_FAULT;
            hasSensorFault = true;
        }
        if (tds.status == STATUS_DISCONNECTED || tds.status == STATUS_STUCK ||
            tds.status == STATUS_ERROR || tds.status == STATUS_OVER_RANGE) {
            hasSensorFault = true;
        }

        // 5. Calibration Pending Flag (Any sensor lacking experimentally verified calibration)
        bool anyMissingCurve = (
            ph.status == STATUS_CALIBRATION_PENDING ||
            turb.status == STATUS_CALIBRATION_PENDING ||
            tds.status == STATUS_CALIBRATION_PENDING
        );
        bool anyCalPending = anyMissingCurve || phProvisional || turbProvisional;
        if (anyCalPending) {
            _healthCode |= HEALTH_CALIBRATION_PENDING;
        }

        // 6. Compute WQS & Evaluate Critical Hazard Override (Sections 7 & 8)
        // Displayed model estimates never become WQS hazards before physical
        // standards verify them; this also prevents provisional-only buzzers.
        bool phMeasValid = isCalibratedValidReading(ph) && !phProvisional;
        bool turbMeasValid = isCalibratedValidReading(turb) && !turbProvisional;
        bool tdsMeasValid = isCalibratedValidReading(tds);
        // Only experimentally calibrated turbidity out-of-range triggers acoustic hazard override;
        // provisional config.h curves mismatching hardware voltage report OUT-OF-RNG without false siren.
        bool turbOutOfCalRange = (turb.status == STATUS_OUT_OF_CAL_RANGE) && !turbProvisional;
        bool anyOutOfRangeReading = (ph.status == STATUS_OUT_OF_CAL_RANGE || turb.status == STATUS_OUT_OF_CAL_RANGE);

        _wqsResult = evaluateWaterQualityAndHazards(
            phMeasValid, ph.calibratedValue,
            turbMeasValid, turb.calibratedValue, turbOutOfCalRange,
            tdsMeasValid, tds.calibratedValue,
            hasSensorFault || hasOverRange || anyMissingCurve || anyOutOfRangeReading || (tds.status == STATUS_DRY_OR_NOT_IMMERSED),
            FEATURE_DEMO_MODE
        );

        // 7. Independent Calibrated Threshold Evaluation with Hysteresis
        // STRICT RULE: Evaluate ONLY valid, finite readings!
        const ModeThresholds& th = getActiveThresholds();
        AlertSeverity phSev = phProvisional ? SEVERITY_NORMAL : evaluatePhThreshold(ph, th);
        AlertSeverity turbSev = turbProvisional ? SEVERITY_NORMAL : evaluateTurbidityThreshold(turb, th);
        if (phProvisional) _phViolated = false;
        if (turbProvisional) _turbViolated = false;
        AlertSeverity tdsSev = evaluateTdsThreshold(tds, th);

        // Max calibrated threshold violation severity (drives buzzer strictly!)
        _thresholdSeverity = phSev;
        if (turbSev > _thresholdSeverity) _thresholdSeverity = turbSev;
        if (tdsSev > _thresholdSeverity)  _thresholdSeverity = tdsSev;

        // 8. Critical Hazard Override takes precedence over normal alerts (Section 8)
        // Never fires on disconnected, missing, or hardware acquisition failures.
        if (_wqsResult.criticalHazard) {
            _severity = SEVERITY_CRITICAL;
            _thresholdSeverity = SEVERITY_CRITICAL;
            if (_wqsResult.hazardPh)   _phViolated = true;
            if (_wqsResult.hazardTds)  _tdsViolated = true;
            if (_wqsResult.hazardTurb || _wqsResult.hazardTurbRange) _turbViolated = true;
            buildHazardMessage();
            return;
        }

        // Build exact alert description identifying every violated parameter
        if (hasThresholdViolation()) {
            _severity = _thresholdSeverity;
            buildViolationMessage();
            return;
        }

        // Note: Disconnected/Faulty sensors update severity & health bitmask for OLED/Cloud,
        // WITHOUT activating threshold violation or buzzer!
        if (hasOverRange) {
            _severity = SEVERITY_SENSOR_FAULT;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "ADC OVER-RANGE!");
            return;
        }
        if (hasSensorFault) {
            _severity = SEVERITY_SENSOR_FAULT;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "PROBE DISCONNECTED");
            return;
        }
        if (tds.status == STATUS_DRY_OR_NOT_IMMERSED) {
            _severity = SEVERITY_NORMAL;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "TDS DRY / NOT IMMERSED");
            return;
        }
        if (ph.status == STATUS_OUT_OF_CAL_RANGE || turb.status == STATUS_OUT_OF_CAL_RANGE) {
            _severity = SEVERITY_SENSOR_FAULT;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "OUT OF CAL RANGE");
            return;
        }
        if (anyMissingCurve) {
            _severity = SEVERITY_NORMAL;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "CAL CONSTANTS NEEDED");
            return;
        }
        if (anyCalPending) {
            _severity = SEVERITY_NORMAL;
            snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "PROVISIONAL ESTIMATE");
            return;
        }

        // All valid sensors within active mode thresholds
        _severity = SEVERITY_NORMAL;
        snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "WATER %s", getWaterStatusName(_wqsResult.waterStatusCode));
    }

    bool shouldSoundBuzzer() const {
        return (_wqsResult.criticalHazard || hasThresholdViolation()) && (_thresholdSeverity >= SEVERITY_WARNING);
    }

    bool hasThresholdViolation() const {
        return _phViolated || _turbViolated || _tdsViolated;
    }

    bool isPhViolated() const { return _phViolated; }
    bool isTurbViolated() const { return _turbViolated; }
    bool isTdsViolated() const { return _tdsViolated; }

    bool isWqsValid() const { return _wqsResult.wqsValid; }
    float getWqs() const { return _wqsResult.wqs; }
    float getSubIndexPh() const { return _wqsResult.qPh; }
    float getSubIndexTds() const { return _wqsResult.qTds; }
    float getSubIndexTurb() const { return _wqsResult.qTurb; }
    bool isCriticalHazard() const { return _wqsResult.criticalHazard; }
    int getWaterStatusCode() const { return _wqsResult.waterStatusCode; }
    const char* getWaterStatusLabel() const { return getWaterStatusName(_wqsResult.waterStatusCode); }

    AlertSeverity getSeverity() const { return _severity; }
    AlertSeverity getThresholdSeverity() const { return _thresholdSeverity; }
    uint16_t getHealthCode() const { return _healthCode; }
    const char* getAlertMessage() const { return _activeAlertMessage; }

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
    WaterQualityMode _mode;
    ModeThresholds _drinkingThresholds;
    ModeThresholds _regularThresholds;
    AlertSeverity _severity;
    AlertSeverity _thresholdSeverity;
    uint16_t _healthCode;
    bool _phViolated;
    bool _turbViolated;
    bool _tdsViolated;
    WqsEvaluationResult _wqsResult;
    char _activeAlertMessage[32];

    static bool isCalibratedValidReading(const SensorReading& r) {
        return (
            r.isValid &&
            r.status != STATUS_CALIBRATION_PENDING &&
            r.status != STATUS_UNAVAILABLE &&
            r.status != STATUS_DISCONNECTED &&
            r.status != STATUS_DRY_OR_NOT_IMMERSED &&
            r.status != STATUS_OVER_RANGE &&
            r.status != STATUS_STUCK &&
            r.status != STATUS_ERROR &&
            r.status != STATUS_OUT_OF_CAL_RANGE &&
            !isnan(r.calibratedValue) &&
            !isinf(r.calibratedValue)
        );
    }

    AlertSeverity evaluatePhThreshold(const SensorReading& ph, const ModeThresholds& th) {
        if (!isCalibratedValidReading(ph)) {
            _phViolated = false;
            return SEVERITY_NORMAL;
        }

        float v = ph.calibratedValue;
        float hyst = min(THRESHOLD_PH_HYSTERESIS, (th.phMax - th.phMin) * 0.25f);

        if (_phViolated) {
            if (v >= (th.phMin + hyst) && v <= (th.phMax - hyst)) {
                _phViolated = false;
            }
        } else {
            if (v < th.phMin || v > th.phMax) {
                _phViolated = true;
            }
        }

        if (!_phViolated) return SEVERITY_NORMAL;
        if (v < th.phCritLow || v > th.phCritHigh) return SEVERITY_CRITICAL;
        return SEVERITY_WARNING;
    }

    AlertSeverity evaluateTurbidityThreshold(const SensorReading& turb, const ModeThresholds& th) {
        if (!isCalibratedValidReading(turb)) {
            _turbViolated = false;
            return SEVERITY_NORMAL;
        }

        float v = turb.calibratedValue;
        float hyst = min(THRESHOLD_TURB_HYSTERESIS, th.turbMax * 0.15f);

        if (_turbViolated) {
            if (v <= (th.turbMax - hyst)) {
                _turbViolated = false;
            }
        } else {
            if (v > th.turbMax) {
                _turbViolated = true;
            }
        }

        if (!_turbViolated) return SEVERITY_NORMAL;
        if (v >= th.turbCritMax) return SEVERITY_CRITICAL;
        return SEVERITY_WARNING;
    }

    AlertSeverity evaluateTdsThreshold(const SensorReading& tds, const ModeThresholds& th) {
        if (!isCalibratedValidReading(tds)) {
            _tdsViolated = false;
            return SEVERITY_NORMAL;
        }

        float v = tds.calibratedValue;
        float hyst = min(THRESHOLD_TDS_HYSTERESIS, th.tdsMax * 0.10f);

        if (_tdsViolated) {
            if (v <= (th.tdsMax - hyst)) {
                _tdsViolated = false;
            }
        } else {
            if (v > th.tdsMax) {
                _tdsViolated = true;
            }
        }

        if (!_tdsViolated) return SEVERITY_NORMAL;
        if (v >= th.tdsCritMax) return SEVERITY_CRITICAL;
        return SEVERITY_WARNING;
    }

    void buildViolationMessage() {
        String msg = "";
        if (_phViolated)   msg += "pH";
        if (_turbViolated) msg += (msg.length() > 0 ? "+TURB" : "TURB");
        if (_tdsViolated)  msg += (msg.length() > 0 ? "+TDS" : "TDS");
        msg += " EXCEEDED";
        snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "%s", msg.c_str());
    }

    void buildHazardMessage() {
        String msg = "HAZARD:";
        if (_wqsResult.hazardPh)        msg += " pH";
        if (_wqsResult.hazardTds)       msg += " TDS";
        if (_wqsResult.hazardTurb)      msg += " TURB";
        if (_wqsResult.hazardTurbRange) msg += " TURB-RNG";
        snprintf(_activeAlertMessage, sizeof(_activeAlertMessage), "%s", msg.c_str());
    }
};
