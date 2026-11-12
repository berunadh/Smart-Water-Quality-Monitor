#pragma once

#include <Arduino.h>
#include <Preferences.h>
#include "SensorBase.h"
#include "TDSSensorLogic.h"

/**
 * ============================================================================
 * TDS SENSOR DRIVER (ANALOG TDS PROBE ON GPIO35 - DIRECT 3.3V CONNECTION)
 * ============================================================================
 * Hardware Wiring:
 * - TDS Meter V1.0 'A' (Analog Out) -> ESP32 GPIO35 (ADC1_CH7, Input Only)
 * - TDS Meter V1.0 '+' (Power)      -> ESP32 3V3
 * - TDS Meter V1.0 '-' (Ground)     -> Common GND
 * - Voltage Divider: NONE (TDS_VOLTAGE_MULTIPLIER = 1.00f; V_module == V_ADC)
 *
 * Electrical & ADC Measurement Notes:
 * - DO NOT apply pH/turbidity 2.5x voltage divider multiplier to TDS.
 * - Uses ESP32 factory-calibrated analogReadMilliVolts() for TDS voltage
 *   accuracy alongside analogRead() raw counts (to catch >= 4000 over-range
 *   and the 0-2 count ADC1 11dB bottom deadzone).
 * - pH and Turbidity conversion in SensorBase remains strictly untouched.
 * - Monitor ADC pin voltage against ADC_OVER_RANGE_VOLTS (3.05V) safety limit.
 *
 * Calibration & Physical Limitations:
 * - Until physical calibration with a certified TDS standard (e.g. 342 ppm NaCl)
 *   is completed, verified, and committed, status stays STATUS_CALIBRATION_PENDING
 *   and calibratedValue = NAN. Never report raw voltage as ppm.
 * - Polynomial assumes ~25 deg C nominal temperature (no temperature sensor/comp).
 * - Single-point calibration does NOT prove SEN0244 curve accuracy across the full
 *   0-3000 ppm range or validate generic "TDS Meter V1.0" board clones.
 * - Voltage alone cannot always distinguish dry air from ultra-pure/distilled
 *   water if both fall near the same baseline or ADC deadzone.
 *
 * Calibration Mathematics (25 deg C nominal standard cubic polynomial):
 *   TDS_raw(V) = (133.42 * V^3 - 255.86 * V^2 + 857.39 * V) * 0.5
 *   kFactor    = TDS_reference_ppm / TDS_raw(V_measured)
 *   TDS(V)     = TDS_raw(V) * kFactor
 * ============================================================================
 */

struct TdsCalSnapshot {
    bool isCalibrated;
    float kFactor;
    float vStandard;
    float ppmStandard;
};

class TDSSensor : public SensorBase {
public:
    TDSSensor(uint8_t pin = PIN_TDS_ADC)
        : _pin(pin),
          _enabled(FEATURE_TDS_ENABLED),
          _isCalibrated(false),
          _kFactor(TDS_CORRECTION_FACTOR),
          _vStandard(0.0f),
          _ppmStandard(0.0f),
          _hasDryBaseline(false),
          _vDryBaseline(0.0f),
          _stuckCounter(0),
          _lastVoltage(-1.0f) {
        snprintf(_nvsDiag, sizeof(_nvsDiag), "Not checked yet");
    }

    static TdsConfigBounds getBounds() {
        TdsConfigBounds b;
        b.disconnectedVolts = ADC_TDS_DISCONNECTED_VOLTS;
        b.overRangeVolts = ADC_OVER_RANGE_VOLTS;
        b.overRangeRaw = (float)ADC_OVER_RANGE_RAW;
        b.zeroDeadbandRaw = ADC_TDS_ZERO_DEADBAND_RAW;
        b.dryMarginVolts = TDS_DRY_MARGIN_VOLTS;
        b.dryMaxBaselineVolts = TDS_DRY_MAX_BASELINE_VOLTS;
        b.calMinVolts = TDS_CAL_MIN_VOLTS;
        b.calMaxVolts = TDS_CAL_MAX_VOLTS;
        b.calMaxStdDevVolts = TDS_CAL_MAX_STDDEV_VOLTS;
        b.calMinPpm = TDS_CAL_MIN_PPM;
        b.calMaxPpm = TDS_CAL_MAX_PPM;
        b.kFactorMin = TDS_KFACTOR_MIN;
        b.kFactorMax = TDS_KFACTOR_MAX;
        b.maxPlausiblePpm = TDS_MAX_PLAUSIBLE_PPM;
        b.verifyTolerancePct = TDS_VERIFY_TOLERANCE_PCT;
        return b;
    }

    void begin() override {
        if (_enabled) {
            pinMode(_pin, INPUT);
            loadCalibration();
        }
    }

    bool isAvailable() const override {
        return _enabled;
    }

    bool isCalibrated() const override {
        return _isCalibrated;
    }

    bool isModelActive() const {
        return _enabled && (_isCalibrated || TDS_USE_POLYNOMIAL_MODEL);
    }

    float getKFactor() const { return _kFactor; }
    float getVStandard() const { return _vStandard; }
    float getPpmStandard() const { return _ppmStandard; }
    bool hasDryBaseline() const { return _hasDryBaseline; }
    float getDryBaselineVoltage() const { return _vDryBaseline; }
    const char* getNvsDiagnostic() const { return _nvsDiag; }

    void enable(bool enabled = true) {
        _enabled = enabled;
        if (_enabled) {
            pinMode(_pin, INPUT);
        }
    }

    void resetStuckDetector() {
        _stuckCounter = 0;
        _lastVoltage = -1.0f;
    }

    /**
     * Unscaled empirical polynomial for 3.3V Analog TDS Meter (ppm / mg/L at ~25C).
     * Expects physical ADC pin voltage (V), NOT voltage-divider scaled voltage.
     */
    static float computeRawPolynomialPpm(float vAdc) {
        return computeTdsRawPolynomialPpm(vAdc);
    }

    /**
     * Collects 30 oversampled readings using ESP32 calibrated millivolts (1.0x direct,
     * NO divider scaling) and returns average voltage, stdDev, and optionally avg raw ADC.
     */
    bool acquireCalibrationReading(float& avgVoltage, float& stdDev, float* outAvgRawAdc = nullptr) {
        const uint8_t sampleCount = 30;
        const uint16_t delayMs = 80;

        float voltages[30];
        float sumV = 0.0f;
        float sumRaw = 0.0f;

        for (uint8_t i = 0; i < sampleCount; i++) {
            float raw = 0.0f;
            float volt = 0.0f;
            sampleTdsTrimmed(15, 2, raw, volt);
            voltages[i] = volt;
            sumV += volt;
            sumRaw += raw;
            if (delayMs > 0) delay(delayMs);
        }

        avgVoltage = sumV / (float)sampleCount;
        if (outAvgRawAdc != nullptr) {
            *outAvgRawAdc = sumRaw / (float)sampleCount;
        }

        float varSum = 0.0f;
        for (uint8_t i = 0; i < sampleCount; i++) {
            float diff = voltages[i] - avgVoltage;
            varSum += diff * diff;
        }
        stdDev = sqrtf(varSum / (float)sampleCount);
        return true;
    }

    TdsCalSnapshot snapshotCalibration() const {
        TdsCalSnapshot snap;
        snap.isCalibrated = _isCalibrated;
        snap.kFactor = _kFactor;
        snap.vStandard = _vStandard;
        snap.ppmStandard = _ppmStandard;
        return snap;
    }

    void restoreCalibration(const TdsCalSnapshot& snap) {
        _isCalibrated = snap.isCalibrated;
        _kFactor = snap.kFactor;
        _vStandard = snap.vStandard;
        _ppmStandard = snap.ppmStandard;
        resetStuckDetector();
    }

    /**
     * Derives and validates the TDS cell constant (kFactor) from a physical standard solution.
     * Supports saveToNvs=false for transactional verification before flash commit.
     */
    bool setCalibrationFromReference(float knownTdsPpm, float measuredAdcVoltage, bool saveToNvs = true, float avgRawAdc = 1000.0f) {
        TdsConfigBounds b = getBounds();
        TdsProposalEvaluation eval = evaluateTdsCalibrationProposal(
            _enabled,
            measuredAdcVoltage,
            0.0f, // Stability validated during acquireCalibrationReading
            avgRawAdc,
            knownTdsPpm,
            _hasDryBaseline,
            _vDryBaseline,
            b
        );

        if (!eval.accepted) {
            Serial.printf("[CAL-TDS] ERROR: Calibration parameters failed validation (code=%d).\n", (int)eval.status);
            return false;
        }

        _kFactor = eval.candidateKFactor;
        _vStandard = measuredAdcVoltage;
        _ppmStandard = knownTdsPpm;
        _isCalibrated = true;
        resetStuckDetector();

        if (saveToNvs) {
            return saveCalibration();
        }
        return true;
    }

    /**
     * Direct kFactor setter (for explicit verified coefficients). Validates bounds strictly.
     */
    bool setCalibration(float kFactor, bool saveToNvs = true) {
        if (kFactor < TDS_KFACTOR_MIN || kFactor > TDS_KFACTOR_MAX) {
            return false;
        }
        _kFactor = kFactor;
        _isCalibrated = true;
        resetStuckDetector();
        if (saveToNvs) {
            return saveCalibration();
        }
        return true;
    }

    /**
     * Records an explicit hardware-measured dry-air baseline voltage in NVS.
     */
    bool setDryBaseline(float avgVoltage, bool saveToNvs = true) {
        if (isnan(avgVoltage) || isinf(avgVoltage) || avgVoltage < 0.0f || avgVoltage >= TDS_DRY_MAX_BASELINE_VOLTS) {
            return false;
        }
        _hasDryBaseline = true;
        _vDryBaseline = avgVoltage;

        if (saveToNvs) {
            Preferences prefs;
            if (!prefs.begin("watersens", false)) {
                return false;
            }
            prefs.putBool("tds_dry_set", true);
            prefs.putFloat("tds_dry_v", _vDryBaseline);
            prefs.end();
        }
        return true;
    }

    void clearDryBaseline() {
        _hasDryBaseline = false;
        _vDryBaseline = 0.0f;
        Preferences prefs;
        if (prefs.begin("watersens", false)) {
            prefs.remove("tds_dry_set");
            prefs.remove("tds_dry_v");
            prefs.end();
        }
    }

    void resetCalibration() {
        _isCalibrated = false;
        _kFactor = TDS_CORRECTION_FACTOR;
        _vStandard = 0.0f;
        _ppmStandard = 0.0f;
        resetStuckDetector();

        Preferences prefs;
        if (prefs.begin("watersens", false)) {
            prefs.remove("tds_cal");
            prefs.remove("tds_k");
            prefs.remove("tds_vs");
            prefs.remove("tds_ref");
            prefs.end();
            Serial.println(F("[CAL-TDS] TDS calibration erased from NVS. Reverted to provisional 25C model."));
        }
    }

    void loadCalibration() {
        Preferences prefs;
        if (!prefs.begin("watersens", true)) {
            // Namespace does not exist yet: initialize RW non-destructively without erasing NVS
            if (prefs.begin("watersens", false)) {
                prefs.end();
                snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' initialized; polynomial model active (k=%.3f)",
                         _kFactor);
            } else {
                snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' NVS open FAILED");
            }
            _isCalibrated = false;
            _kFactor = TDS_CORRECTION_FACTOR;
            Serial.printf("[CAL-NVS] TDS: %s\n", _nvsDiag);
            return;
        }

        bool hasCal = prefs.isKey("tds_cal");
        bool cal = hasCal ? prefs.getBool("tds_cal", false) : false;
        if (cal) {
            float k = prefs.getFloat("tds_k", 0.0f);
            float vs = prefs.getFloat("tds_vs", 0.0f);
            float ref = prefs.getFloat("tds_ref", 0.0f);
            if (!isnan(k) && !isinf(k) &&
                k >= TDS_KFACTOR_MIN && k <= TDS_KFACTOR_MAX &&
                vs >= TDS_CAL_MIN_VOLTS && vs <= TDS_CAL_MAX_VOLTS &&
                ref >= TDS_CAL_MIN_PPM && ref <= TDS_CAL_MAX_PPM) {
                _kFactor = k;
                _vStandard = vs;
                _ppmStandard = ref;
                _isCalibrated = true;
                snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' OK; tds_cal=true; k=%.4f (VALID)", _kFactor);
                Serial.printf("[CAL] Loaded TDS calibration from NVS: k=%.4f (Ref %.0f ppm @ %.3fV)\n",
                              _kFactor, _ppmStandard, _vStandard);
            } else {
                _isCalibrated = false;
                _kFactor = TDS_CORRECTION_FACTOR;
                snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' OK; tds_cal=true REJECTED; using model k=%.3f",
                         _kFactor);
            }
        } else {
            _isCalibrated = false;
            _kFactor = TDS_CORRECTION_FACTOR;
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "Namespace 'watersens' OK; %s; polynomial model @ %.1fC (k=%.3f)",
                     hasCal ? "tds_cal=false" : "no tds_cal key",
                     TDS_NOMINAL_TEMP_C, _kFactor);
        }

        bool drySet = prefs.getBool("tds_dry_set", false);
        if (drySet) {
            float dryV = prefs.getFloat("tds_dry_v", -1.0f);
            if (!isnan(dryV) && dryV >= 0.0f && dryV < TDS_DRY_MAX_BASELINE_VOLTS) {
                _hasDryBaseline = true;
                _vDryBaseline = dryV;
                Serial.printf("[CAL] Loaded TDS dry baseline from NVS: V_dry=%.3fV (+%.3fV margin)\n",
                              _vDryBaseline, TDS_DRY_MARGIN_VOLTS);
            }
        }
        prefs.end();
    }

    bool saveCalibration() {
        Preferences prefs;
        if (!prefs.begin("watersens", false)) {
            Serial.println(F("[CAL-TDS] ERROR: Unable to open NVS namespace 'watersens' for write."));
            return false;
        }
        prefs.putBool("tds_cal", true);
        prefs.putFloat("tds_k", _kFactor);
        prefs.putFloat("tds_vs", _vStandard);
        prefs.putFloat("tds_ref", _ppmStandard);
        prefs.end();
        return verifyNvsReadback(_kFactor, _vStandard, _ppmStandard);
    }

    /**
     * Reads back TDS calibration from NVS and verifies exact match with expected values.
     */
    bool verifyNvsReadback(float expectedK, float expectedVStd, float expectedPpmStd) const {
        Preferences prefs;
        if (!prefs.begin("watersens", true)) {
            return false;
        }
        bool cal = prefs.getBool("tds_cal", false);
        float k = prefs.getFloat("tds_k", 0.0f);
        float vs = prefs.getFloat("tds_vs", 0.0f);
        float ref = prefs.getFloat("tds_ref", 0.0f);
        prefs.end();

        return cal &&
               fabsf(k - expectedK) < 1e-4f &&
               fabsf(vs - expectedVStd) < 1e-4f &&
               fabsf(ref - expectedPpmStd) < 1e-2f;
    }

    SensorReading read() override {
        SensorReading reading;
        memset(&reading, 0, sizeof(reading));
        reading.rawAdc = 0.0f;
        reading.adcVoltage = 0.0f;
        reading.reconstructedVoltage = 0.0f;
        reading.calibratedValue = NAN; // Strictly NAN until valid & calibrated

        if (!_enabled) {
            reading.status = STATUS_UNAVAILABLE;
            reading.isValid = false;
            snprintf(reading.message, sizeof(reading.message), "N/A (DISABLED)");
            return reading;
        }

        // 1. Hardware Acquisition on GPIO35 (Direct 1.0x, factory-calibrated millivolts)
        sampleTdsTrimmed(ADC_OVERSAMPLE_SAMPLES, ADC_SAMPLE_DELAY_MS, reading.rawAdc, reading.adcVoltage);
        reading.reconstructedVoltage = reading.adcVoltage * TDS_VOLTAGE_MULTIPLIER; // Strictly 1.00x!

        TdsConfigBounds b = getBounds();

        // 2. Track natural variance only on active liquid signals (above dry/deadzone floor)
        bool isLowOrDry = (reading.adcVoltage < b.disconnectedVolts) ||
                          (reading.rawAdc < b.zeroDeadbandRaw) ||
                          (_hasDryBaseline && reading.adcVoltage <= (_vDryBaseline + b.dryMarginVolts));
        bool isStuck = false;
        if (!isLowOrDry && !isOverRange(reading.rawAdc, reading.adcVoltage)) {
            isStuck = isStableVoltageFault(reading.adcVoltage, _lastVoltage, _stuckCounter);
        } else {
            _stuckCounter = 0;
            _lastVoltage = -1.0f;
        }

        // 3. Pure state classification with Section 3 temperature-compensated polynomial
        TdsClassificationResult cls = classifyTdsSignal(
            _enabled,
            _isCalibrated,
            _kFactor,
            reading.rawAdc,
            reading.adcVoltage,
            _hasDryBaseline,
            _vDryBaseline,
            isStuck,
            b,
            TDS_NOMINAL_TEMP_C,
            TDS_USE_POLYNOMIAL_MODEL
        );

        reading.isValid = cls.isValid;
        reading.calibratedValue = cls.calibratedPpm;

        switch (cls.state) {
            case TDS_STATE_UNAVAILABLE:
                reading.status = STATUS_UNAVAILABLE;
                snprintf(reading.message, sizeof(reading.message), "N/A (DISABLED)");
                break;
            case TDS_STATE_OVER_RANGE:
                reading.status = STATUS_OVER_RANGE;
                snprintf(reading.message, sizeof(reading.message), "ADC OVER-RANGE (>3.05V)");
                break;
            case TDS_STATE_DISCONNECTED:
                reading.status = STATUS_DISCONNECTED;
                snprintf(reading.message, sizeof(reading.message), "DISCONNECTED/0V");
                break;
            case TDS_STATE_DRY_OR_NO_SIGNAL:
                reading.status = STATUS_DRY_OR_NOT_IMMERSED;
                snprintf(reading.message, sizeof(reading.message), "DRY/NOT IMMERSED");
                break;
            case TDS_STATE_STUCK:
                reading.status = STATUS_STUCK;
                snprintf(reading.message, sizeof(reading.message), "STUCK READING");
                break;
            case TDS_STATE_CALIBRATION_PENDING:
                reading.status = STATUS_CALIBRATION_PENDING;
                snprintf(reading.message, sizeof(reading.message), "UNCALIBRATED");
                break;
            case TDS_STATE_IMPLAUSIBLE:
                reading.status = STATUS_ERROR;
                snprintf(reading.message, sizeof(reading.message), "IMPLAUSIBLE TDS");
                break;
            case TDS_STATE_VALID_CALIBRATED:
            default:
                if (cls.calibratedPpm > HAZARD_TDS_MAX_PPM) {
                    reading.status = STATUS_CRITICAL;
                } else {
                    reading.status = STATUS_OK;
                }
                snprintf(reading.message, sizeof(reading.message),
                         _isCalibrated ? "%.0f ppm" : "%.0f ppm (PROV)",
                         cls.calibratedPpm);
                break;
        }

        return reading;
    }

private:
    uint8_t _pin;
    bool _enabled;
    bool _isCalibrated;
    float _kFactor;
    float _vStandard;
    float _ppmStandard;
    bool _hasDryBaseline;
    float _vDryBaseline;
    uint8_t _stuckCounter;
    float _lastVoltage;
    char _nvsDiag[144];

    void sampleTdsTrimmed(uint8_t samples, uint16_t delayMs, float& outRaw, float& outVoltage) {
        float adcVolt = 0.0f;
        sampleChannelTrimmedMilliVolts(_pin, samples, delayMs, outRaw, adcVolt);
        outVoltage = adcVolt * TDS_VOLTAGE_MULTIPLIER; // Strictly 1.00x!
    }
};
