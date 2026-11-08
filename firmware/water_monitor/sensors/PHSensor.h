#pragma once

#include <Arduino.h>
#include <Preferences.h>
#include "SensorBase.h"

/**
 * ============================================================================
 * pH SENSOR DRIVER (E201-C ELECTRODE + GREEN SIGNAL CONDITIONING BOARD)
 * ============================================================================
 * Pin: GPIO34 (ADC1_CH6 - Input Only)
 * Circuit: P pin -> 15kΩ -> GPIO34 -> 10kΩ -> GND
 * Reconstructed V_board = V_ADC * 2.500
 * 
 * Calibration Mathematics:
 * - Two-Point Buffer Reference: pH 7.00 (neutral) and pH 4.01 (acidic)
 * - Nernstian slope equation:
 *     ΔV = V_pH7 - V_pH4
 *     Slope m = (7.00 - 4.01) / ΔV = 2.99 / (V_pH7 - V_pH4)
 *     Intercept b = 7.00 - (m * V_pH7)
 *     pH(V) = m * V + b
 * 
 * Physical Validation Rules:
 * - V_pH7 and V_pH4 must be within physical range (0.1V to 4.95V)
 * - Minimum separation |V_pH7 - V_pH4| >= 0.15V
 * - Slope |m| between 0.50 and 12.00 pH/V
 * - Measurement stability standard deviation σ < 0.05V
 * - Persistent storage in ESP32 Flash NVS via Preferences API
 * - Never fabricates calibration coefficients; defaults to STATUS_CALIBRATION_PENDING
 * ============================================================================
 */

class PHSensor : public SensorBase {
public:
    PHSensor(uint8_t pin = PIN_PH_ADC) 
        : _pin(pin), 
          _isCalibrated(false),
          _vPh7(0.0f),
          _vPh4(0.0f),
          _slope(0.0f),
          _intercept(0.0f),
          _stuckCounter(0),
          _lastVoltage(-1.0f) {}

    void begin() override {
        pinMode(_pin, INPUT);
        loadCalibration();
    }

    bool isAvailable() const override {
        return true;
    }

    bool isCalibrated() const override {
        return _isCalibrated;
    }

    float getVPh7() const { return _vPh7; }
    float getVPh4() const { return _vPh4; }
    float getSlope() const { return _slope; }
    float getIntercept() const { return _intercept; }

    /**
     * Samples the probe stably over a series of readings and returns average voltage
     * and standard deviation for calibration validation.
     */
    bool acquireCalibrationReading(float& avgVoltage, float& stdDev) {
        return sampleStableVoltage(_pin, 30, 80, avgVoltage, stdDev);
    }

    /**
     * Sets two-point calibration using measured sensor board voltages
     * in standard buffer solutions (pH 7.00 and pH 4.01) at 25°C.
     * 
     * Validates physical plausibility before saving to non-volatile storage.
     */
    bool setCalibration(float vBoardPh7, float vBoardPh4, bool saveToNvs = true) {
        // 1. Boundary checks: Voltages must be positive and within physical circuit limits
        if (vBoardPh7 < 0.10f || vBoardPh7 > 4.95f || vBoardPh4 < 0.10f || vBoardPh4 > 4.95f) {
            Serial.printf("[CAL] ERROR: Measured voltages out of electrical bounds (V7=%.3fV, V4=%.3fV).\n", 
                          vBoardPh7, vBoardPh4);
            return false;
        }

        // 2. Minimum voltage separation check (|V7 - V4| >= 0.15V)
        float deltaV = vBoardPh7 - vBoardPh4;
        if (abs(deltaV) < 0.15f) {
            Serial.printf("[CAL] ERROR: Insufficient voltage separation between pH 7.00 and pH 4.01 (|ΔV|=%.3fV < 0.15V).\n", 
                          abs(deltaV));
            return false;
        }

        // 3. Compute slope and intercept
        float slope = (7.00f - 4.01f) / deltaV;
        float intercept = 7.00f - (slope * vBoardPh7);

        // 4. Physical slope plausibility check (magnitude between 0.50 and 12.00 pH/V)
        if (abs(slope) < 0.50f || abs(slope) > 12.00f) {
            Serial.printf("[CAL] ERROR: Calculated slope %.3f pH/V is outside plausible physical range (0.5 to 12.0).\n", 
                          slope);
            return false;
        }

        _vPh7 = vBoardPh7;
        _vPh4 = vBoardPh4;
        _slope = slope;
        _intercept = intercept;
        _isCalibrated = true;

        if (saveToNvs) {
            saveCalibration();
        }

        return true;
    }

    /**
     * Safely resets calibration in memory and NVS back to uncalibrated pending state.
     */
    void resetCalibration() {
        _isCalibrated = false;
        _vPh7 = 0.0f;
        _vPh4 = 0.0f;
        _slope = 0.0f;
        _intercept = 0.0f;

        Preferences prefs;
        if (prefs.begin("watersens", false)) {
            prefs.remove("ph_cal");
            prefs.remove("ph_v7");
            prefs.remove("ph_v4");
            prefs.remove("ph_slope");
            prefs.remove("ph_inter");
            prefs.end();
            Serial.println(F("[CAL] pH calibration erased from NVS. Sensor reset to CALIBRATION_PENDING."));
        }
    }

    /**
     * Loads saved calibration coefficients from ESP32 non-volatile storage.
     */
    void loadCalibration() {
        Preferences prefs;
        if (prefs.begin("watersens", true)) { // Read-only mode
            bool cal = prefs.getBool("ph_cal", false);
            if (cal) {
                float v7 = prefs.getFloat("ph_v7", 0.0f);
                float v4 = prefs.getFloat("ph_v4", 0.0f);
                float sl = prefs.getFloat("ph_slope", 0.0f);
                float in = prefs.getFloat("ph_inter", 0.0f);

                if (v7 > 0.1f && v4 > 0.1f && abs(sl) >= 0.50f && abs(sl) <= 12.00f) {
                    _vPh7 = v7;
                    _vPh4 = v4;
                    _slope = sl;
                    _intercept = in;
                    _isCalibrated = true;
                    Serial.printf("[CAL] Loaded pH calibration from NVS: V7=%.3fV, V4=%.3fV, Slope=%.3f pH/V, Intercept=%.3f\n",
                                  _vPh7, _vPh4, _slope, _intercept);
                } else {
                    _isCalibrated = false;
                }
            } else {
                _isCalibrated = false;
            }
            prefs.end();
        }
    }

    /**
     * Commits valid calibration parameters to ESP32 flash partition.
     */
    void saveCalibration() {
        Preferences prefs;
        if (prefs.begin("watersens", false)) { // Read-write mode
            prefs.putBool("ph_cal", true);
            prefs.putFloat("ph_v7", _vPh7);
            prefs.putFloat("ph_v4", _vPh4);
            prefs.putFloat("ph_slope", _slope);
            prefs.putFloat("ph_inter", _intercept);
            prefs.end();
            Serial.println(F("[CAL] pH calibration successfully stored in persistent flash NVS."));
        }
    }

    SensorReading read() override {
        SensorReading reading;
        memset(&reading, 0, sizeof(reading));
        reading.calibratedValue = NAN;

        // In Demo Mode, simulate clean municipal tap water (pH ~7.28, board ~2.5V, ADC ~1.0V)
        if (FEATURE_DEMO_MODE) {
            reading.rawAdc = 1240.0f + (float)(random(-15, 16));
            reading.adcVoltage = rawToAdcVoltage(reading.rawAdc);
            reading.reconstructedVoltage = adcToReconstructedVoltage(reading.adcVoltage);
            reading.calibratedValue = 7.28f + ((reading.rawAdc - 1240.0f) * 0.005f);
            reading.status = STATUS_OK;
            reading.isValid = true;
            snprintf(reading.message, sizeof(reading.message), "DEMO (NORMAL)");
            return reading;
        }

        // 1. Oversample ADC with trimmed mean
        reading.rawAdc = sampleAdcTrimmed(_pin, ADC_OVERSAMPLE_SAMPLES, ADC_SAMPLE_DELAY_MS);
        reading.adcVoltage = rawToAdcVoltage(reading.rawAdc);
        reading.reconstructedVoltage = adcToReconstructedVoltage(reading.adcVoltage);

        // 2. Electrical Over-Range Safety Check
        if (isOverRange(reading.rawAdc, reading.adcVoltage)) {
            reading.status = STATUS_OVER_RANGE;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "ADC OVER-RANGE (>3.05V)");
            return reading;
        }

        // 3. Disconnected / Open-Circuit Check
        if (reading.adcVoltage < ADC_DISCONNECTED_VOLTS) {
            reading.status = STATUS_DISCONNECTED;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "DISCONNECTED/GND");
            return reading;
        }

        // 4. Stuck reading detection (checks if ADC has zero natural jitter over successive reads)
        if (_lastVoltage > 0.0f && abs(reading.adcVoltage - _lastVoltage) < 0.0005f) {
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

        // 5. Calibration check: If uncalibrated, electrical acquisition is valid, but value is strictly NaN
        if (!_isCalibrated) {
            reading.status = STATUS_CALIBRATION_PENDING;
            reading.isValid = true; // Signal board reading is electrically healthy
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "CALIBRATION PENDING");
            return reading;
        }

        // 6. Compute calibrated pH using linear calibration model
        float ph = (_slope * reading.reconstructedVoltage) + _intercept;

        // 7. Plausibility sanity bounds (physical pH is 0.0 to 14.0)
        if (ph < 0.0f || ph > 14.0f) {
            reading.status = STATUS_ERROR;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "IMPLAUSIBLE pH (%.1f)", ph);
            return reading;
        }

        reading.calibratedValue = ph;
        reading.isValid = true;

        // 8. Water quality threshold classification
        if (ph < THRESHOLD_PH_CRITICAL_MIN || ph > THRESHOLD_PH_CRITICAL_MAX) {
            reading.status = STATUS_CRITICAL;
            snprintf(reading.message, sizeof(reading.message), "CRITICAL pH (%.2f)", ph);
        } else if (ph < THRESHOLD_PH_WARNING_MIN || ph > THRESHOLD_PH_WARNING_MAX) {
            reading.status = STATUS_WARNING;
            snprintf(reading.message, sizeof(reading.message), "pH OUT OF RANGE");
        } else {
            reading.status = STATUS_OK;
            snprintf(reading.message, sizeof(reading.message), "NORMAL (%.2f)", ph);
        }

        return reading;
    }

private:
    uint8_t _pin;
    bool _isCalibrated;
    float _vPh7;
    float _vPh4;
    float _slope;
    float _intercept;
    uint8_t _stuckCounter;
    float _lastVoltage;
};
