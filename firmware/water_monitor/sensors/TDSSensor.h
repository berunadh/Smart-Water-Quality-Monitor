#pragma once

#include <Arduino.h>
#include <Preferences.h>
#include "SensorBase.h"

/**
 * ============================================================================
 * TDS SENSOR DRIVER (ANALOG TDS PROBE ON GPIO35 - DIRECT 3.3V CONNECTION)
 * ============================================================================
 * Pin: GPIO35 (ADC1_CH7 - Input Only)
 * Supply: 3V3 and GND
 * Voltage Divider: NONE (TDS_VOLTAGE_MULTIPLIER = 1.00f; V_module == V_ADC)
 * 
 * Electrical & Data Contract:
 * - DO NOT apply pH/turbidity 2.5x voltage divider multiplier to TDS.
 * - Monitor ADC pin voltage against ADC_OVER_RANGE_VOLTS (3.05V) safety limit.
 * - Until physical calibration with a known TDS standard solution is completed
 *   and confirmed, status stays STATUS_CALIBRATION_PENDING and calibratedValue = NAN.
 * - Never report raw voltage as ppm. Never fabricate default kFactor calibration.
 * 
 * Calibration Mathematics (25°C nominal standard cubic polynomial):
 *   TDS_raw(V) = (133.42 * V^3 - 255.86 * V^2 + 857.39 * V) * 0.5
 *   kFactor = TDS_reference / TDS_raw(V_measured)
 *   TDS(V) = TDS_raw(V) * kFactor
 * ============================================================================
 */

class TDSSensor : public SensorBase {
public:
    TDSSensor(uint8_t pin = PIN_TDS_ADC) 
        : _pin(pin), 
          _enabled(FEATURE_TDS_ENABLED), 
          _isCalibrated(false),
          _kFactor(0.0f),
          _vStandard(0.0f),
          _ppmStandard(0.0f),
          _stuckCounter(0),
          _lastVoltage(-1.0f) {}

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

    float getKFactor() const { return _kFactor; }
    float getVStandard() const { return _vStandard; }
    float getPpmStandard() const { return _ppmStandard; }

    void enable(bool enabled = true) {
        _enabled = enabled;
        if (_enabled) {
            pinMode(_pin, INPUT);
        }
    }

    /**
     * Unscaled empirical polynomial for 3.3V Analog TDS Meter (mg/L at 25°C).
     * Expects raw ADC voltage (0.0 - 3.0V), NOT voltage-divider scaled voltage.
     */
    static float computeRawPolynomialPpm(float vAdc) {
        if (vAdc <= 0.0f) return 0.0f;
        float poly = (133.42f * vAdc * vAdc * vAdc - 255.86f * vAdc * vAdc + 857.39f * vAdc) * 0.5f;
        return (poly > 0.0f) ? poly : 0.0f;
    }

    /**
     * Collects 30 oversampled readings using direct 1.0x multiplier (NO divider scaling).
     */
    bool acquireCalibrationReading(float& avgVoltage, float& stdDev) {
        return sampleStableVoltage(_pin, 30, 80, avgVoltage, stdDev, TDS_VOLTAGE_MULTIPLIER);
    }

    /**
     * Derives and validates the TDS cell constant (kFactor) from a physical standard solution.
     */
    bool setCalibrationFromReference(float knownTdsPpm, float measuredAdcVoltage, bool saveToNvs = true) {
        // 1. Validate electrical input bounds for direct 3.3V connection
        if (measuredAdcVoltage < 0.10f || measuredAdcVoltage > 2.95f) {
            Serial.printf("[CAL-TDS] ERROR: Measured ADC voltage %.3fV out of calibration bounds (0.10V - 2.95V).\n",
                          measuredAdcVoltage);
            return false;
        }

        // 2. Validate reference concentration bounds
        if (knownTdsPpm < 10.0f || knownTdsPpm > 3000.0f) {
            Serial.printf("[CAL-TDS] ERROR: Reference concentration %.1f ppm outside plausible range (10 - 3000 ppm).\n",
                          knownTdsPpm);
            return false;
        }

        // 3. Compute cell constant k = Known / RawPolynomial(V)
        float rawPoly = computeRawPolynomialPpm(measuredAdcVoltage);
        if (rawPoly < 5.0f) {
            Serial.println(F("[CAL-TDS] ERROR: Polynomial baseline too low for reliable kFactor division."));
            return false;
        }

        float k = knownTdsPpm / rawPoly;
        if (k < 0.15f || k > 5.00f) {
            Serial.printf("[CAL-TDS] ERROR: Derived kFactor %.3f outside physically plausible limits (0.15 - 5.00).\n", k);
            return false;
        }

        _kFactor = k;
        _vStandard = measuredAdcVoltage;
        _ppmStandard = knownTdsPpm;
        _isCalibrated = true;

        if (saveToNvs) {
            saveCalibration();
        }
        return true;
    }

    /**
     * Direct kFactor setter (for explicit verified coefficients). Validates bounds strictly.
     */
    bool setCalibration(float kFactor, bool saveToNvs = true) {
        if (kFactor < 0.15f || kFactor > 5.00f) {
            return false;
        }
        _kFactor = kFactor;
        _isCalibrated = true;
        if (saveToNvs) {
            saveCalibration();
        }
        return true;
    }

    void resetCalibration() {
        _isCalibrated = false;
        _kFactor = 0.0f;
        _vStandard = 0.0f;
        _ppmStandard = 0.0f;

        Preferences prefs;
        if (prefs.begin("watersens", false)) {
            prefs.remove("tds_cal");
            prefs.remove("tds_k");
            prefs.remove("tds_vs");
            prefs.remove("tds_ref");
            prefs.end();
            Serial.println(F("[CAL-TDS] TDS calibration erased from NVS. Reverted to CALIBRATION_PENDING."));
        }
    }

    void loadCalibration() {
        Preferences prefs;
        if (prefs.begin("watersens", true)) {
            bool cal = prefs.getBool("tds_cal", false);
            if (cal) {
                float k = prefs.getFloat("tds_k", 0.0f);
                float vs = prefs.getFloat("tds_vs", 0.0f);
                float ref = prefs.getFloat("tds_ref", 0.0f);
                if (k >= 0.15f && k <= 5.00f) {
                    _kFactor = k;
                    _vStandard = vs;
                    _ppmStandard = ref;
                    _isCalibrated = true;
                    Serial.printf("[CAL] Loaded TDS calibration from NVS: k=%.3f (Ref %.0f ppm @ %.3fV)\n",
                                  _kFactor, _ppmStandard, _vStandard);
                } else {
                    _isCalibrated = false;
                }
            } else {
                _isCalibrated = false;
            }
            prefs.end();
        }
    }

    void saveCalibration() {
        Preferences prefs;
        if (prefs.begin("watersens", false)) {
            prefs.putBool("tds_cal", true);
            prefs.putFloat("tds_k", _kFactor);
            prefs.putFloat("tds_vs", _vStandard);
            prefs.putFloat("tds_ref", _ppmStandard);
            prefs.end();
            Serial.println(F("[CAL] TDS calibration successfully stored in persistent flash NVS."));
        }
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

        // Demo Simulation Mode (only if FEATURE_DEMO_MODE == true)
        if (FEATURE_DEMO_MODE) {
            reading.rawAdc = 1420.0f + (float)(random(-12, 13));
            reading.adcVoltage = rawToAdcVoltage(reading.rawAdc);
            reading.reconstructedVoltage = reading.adcVoltage; // Direct 1.0x
            reading.calibratedValue = 215.0f + ((reading.rawAdc - 1420.0f) * 0.4f);
            reading.status = STATUS_OK;
            reading.isValid = true;
            snprintf(reading.message, sizeof(reading.message), "DEMO (%.0f ppm)", reading.calibratedValue);
            return reading;
        }

        // 1. Hardware Acquisition on GPIO35 (Direct ADC, NO voltage divider multiplier!)
        reading.rawAdc = sampleAdcTrimmed(_pin, ADC_OVERSAMPLE_SAMPLES, ADC_SAMPLE_DELAY_MS);
        reading.adcVoltage = rawToAdcVoltage(reading.rawAdc);
        reading.reconstructedVoltage = reading.adcVoltage * TDS_VOLTAGE_MULTIPLIER; // Strictly 1.00x!

        // 2. Electrical Over-Range Safety Check (> 3.05V)
        if (isOverRange(reading.rawAdc, reading.adcVoltage)) {
            reading.status = STATUS_OVER_RANGE;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "ADC OVER-RANGE (>3.05V)");
            return reading;
        }

        // 3. Disconnected / Dry-in-Air Check (< 15 mV)
        if (reading.adcVoltage < ADC_TDS_DISCONNECTED_VOLTS) {
            reading.status = STATUS_DISCONNECTED;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "DRY/DISCONNECTED");
            return reading;
        }

        // 4. Stuck Reading Detection (skip near 0V dry state)
        if (_lastVoltage > 0.05f && abs(reading.adcVoltage - _lastVoltage) < 0.0005f) {
            _stuckCounter++;
            if (_stuckCounter > 15) {
                reading.status = STATUS_STUCK;
                reading.isValid = false;
                reading.calibratedValue = NAN;
                snprintf(reading.message, sizeof(reading.message), "STUCK READING");
                return reading;
            }
        } else {
            _stuckCounter = 0;
            _lastVoltage = reading.adcVoltage;
        }

        // 5. Calibration Check: Never compute ppm without valid calibration!
        if (!_isCalibrated || _kFactor <= 0.0f) {
            reading.status = STATUS_CALIBRATION_PENDING;
            reading.isValid = true; // Electrical read is healthy, calibration pending
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "CALIBRATION PENDING");
            return reading;
        }

        // 6. Compute Calibrated TDS ppm using polynomial + calibrated kFactor
        float tds = computeRawPolynomialPpm(reading.adcVoltage) * _kFactor;

        // 7. Physical plausibility bounds check (0 to 5000 ppm)
        if (tds < 0.0f || tds > 5000.0f || isnan(tds) || isinf(tds)) {
            reading.status = STATUS_ERROR;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "IMPLAUSIBLE TDS");
            return reading;
        }

        reading.calibratedValue = tds;
        reading.isValid = true;
        reading.status = STATUS_OK; // Mode-specific thresholds evaluated centrally by SensorValidator
        snprintf(reading.message, sizeof(reading.message), "%.0f ppm", tds);
        return reading;
    }

private:
    uint8_t _pin;
    bool _enabled;
    bool _isCalibrated;
    float _kFactor;
    float _vStandard;
    float _ppmStandard;
    uint8_t _stuckCounter;
    float _lastVoltage;
};
