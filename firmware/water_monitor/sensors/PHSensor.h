#pragma once

#include "SensorBase.h"

/**
 * ============================================================================
 * pH SENSOR DRIVER (E201-C ELECTRODE + GREEN SIGNAL CONDITIONING BOARD)
 * ============================================================================
 * Pin: GPIO34 (ADC1_CH6 - Input Only)
 * Circuit: P pin -> 15kΩ -> GPIO34 -> 10kΩ -> GND
 * Reconstructed V_board = V_ADC * 2.500
 * 
 * Calibration:
 * Supports 2-point (pH 7.00 neutral, pH 4.01 acid) or 3-point calibration.
 * Until real calibration is performed using standard buffer solutions,
 * reports STATUS_CALIBRATION_PENDING. No fabricated calibration constants!
 * ============================================================================
 */

class PHSensor : public SensorBase {
public:
    PHSensor(uint8_t pin = PIN_PH_ADC) 
        : _pin(pin), 
          _isCalibrated(false),
          _vPh7(0.0f),
          _vPh4(0.0f),
          _vPh10(0.0f),
          _hasThreePoint(false),
          _slope(0.0f),
          _intercept(0.0f),
          _stuckCounter(0),
          _lastVoltage(-1.0f) {}

    void begin() override {
        pinMode(_pin, INPUT);
        // ESP32 ADC attenuation is configured globally in setup()
    }

    bool isAvailable() const override {
        return true;
    }

    bool isCalibrated() const override {
        return _isCalibrated;
    }

    /**
     * Sets two-point calibration using measured sensor board voltages
     * in standard buffer solutions at 25°C.
     */
    void setCalibration(float vBoardPh7, float vBoardPh4) {
        if (abs(vBoardPh7 - vBoardPh4) < 0.1f) {
            // Unreasonable calibration points (voltages too close)
            return;
        }
        _vPh7 = vBoardPh7;
        _vPh4 = vBoardPh4;
        _slope = (7.00f - 4.01f) / (_vPh7 - _vPh4);
        _intercept = 7.00f - (_slope * _vPh7);
        _isCalibrated = true;
        _hasThreePoint = false;
    }

    /**
     * Sets three-point calibration using standard buffer solutions
     * pH 7.00, pH 4.01, and pH 10.01.
     */
    void setThreePointCalibration(float vBoardPh7, float vBoardPh4, float vBoardPh10) {
        setCalibration(vBoardPh7, vBoardPh4);
        _vPh10 = vBoardPh10;
        _hasThreePoint = true;
    }

    void resetCalibration() {
        _isCalibrated = false;
        _hasThreePoint = false;
        _vPh7 = 0.0f;
        _vPh4 = 0.0f;
        _slope = 0.0f;
        _intercept = 0.0f;
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

        // 3. Disconnected / Open-Circuit Check (very low voltage or floating near 0V)
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
            if (_stuckCounter > 15) { // 15 consecutive reads with zero variance
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

        // 5. Calibration check
        if (!_isCalibrated) {
            reading.status = STATUS_CALIBRATION_PENDING;
            reading.isValid = true; // Electrical acquisition is good, but value uncalibrated
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "CALIBRATION PENDING");
            return reading;
        }

        // 6. Compute calibrated pH
        float ph = 0.0f;
        if (_hasThreePoint && reading.reconstructedVoltage > _vPh7 && abs(_vPh10 - _vPh7) > 0.1f) {
            // Basic segmented interpolation for alkaline branch
            float alkalineSlope = (10.01f - 7.00f) / (_vPh10 - _vPh7);
            ph = 7.00f + (alkalineSlope * (reading.reconstructedVoltage - _vPh7));
        } else {
            ph = (_slope * reading.reconstructedVoltage) + _intercept;
        }

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
    float _vPh10;
    bool _hasThreePoint;
    float _slope;
    float _intercept;
    uint8_t _stuckCounter;
    float _lastVoltage;
};
