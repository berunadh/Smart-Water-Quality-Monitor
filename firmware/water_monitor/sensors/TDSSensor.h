#pragma once

#include "SensorBase.h"

/**
 * ============================================================================
 * TDS SENSOR DRIVER INTERFACE (RESERVED FOR FUTURE HARDWARE EXPANSION)
 * ============================================================================
 * Reserved Pin: GPIO35 (ADC1_CH7 - Input Only)
 * 
 * CURRENT STATUS: HARDWARE NOT ARRIVED / PENDING INSTALLATION.
 * FEATURE_TDS_ENABLED in config.h is strictly false.
 * 
 * IMPORTANT CONTRACT REQUIREMENT:
 * An uninstalled sensor MUST NEVER report 0.0 ppm.
 * It strictly returns status = STATUS_UNAVAILABLE, isValid = false,
 * and calibratedValue = NAN.
 * ============================================================================
 */

class TDSSensor : public SensorBase {
public:
    TDSSensor(uint8_t pin = PIN_TDS_ADC) 
        : _pin(pin), 
          _enabled(FEATURE_TDS_ENABLED), 
          _isCalibrated(false),
          _kFactor(1.0f) {}

    void begin() override {
        if (_enabled) {
            pinMode(_pin, INPUT);
        }
    }

    bool isAvailable() const override {
        return _enabled;
    }

    bool isCalibrated() const override {
        return _isCalibrated;
    }

    void enable(bool enabled = true) {
        _enabled = enabled;
        if (_enabled) {
            pinMode(_pin, INPUT);
        }
    }

    void setCalibration(float kFactor) {
        if (kFactor > 0.1f && kFactor < 10.0f) {
            _kFactor = kFactor;
            _isCalibrated = true;
        }
    }

    SensorReading read() override {
        SensorReading reading;
        memset(&reading, 0, sizeof(reading));
        reading.rawAdc = 0.0f;
        reading.adcVoltage = 0.0f;
        reading.reconstructedVoltage = 0.0f;
        reading.calibratedValue = NAN; // STRICT REQUIREMENT: never 0.0

        if (!_enabled) {
            reading.status = STATUS_UNAVAILABLE;
            reading.isValid = false;
            snprintf(reading.message, sizeof(reading.message), "N/A (NOT INSTALLED)");
            return reading;
        }

        // Hardware acquisition (ready for when sensor is plugged into GPIO35)
        reading.rawAdc = sampleAdcTrimmed(_pin, ADC_OVERSAMPLE_SAMPLES, ADC_SAMPLE_DELAY_MS);
        reading.adcVoltage = rawToAdcVoltage(reading.rawAdc);
        reading.reconstructedVoltage = adcToReconstructedVoltage(reading.adcVoltage);

        if (isOverRange(reading.rawAdc, reading.adcVoltage)) {
            reading.status = STATUS_OVER_RANGE;
            reading.isValid = false;
            snprintf(reading.message, sizeof(reading.message), "ADC OVER-RANGE");
            return reading;
        }

        if (!_isCalibrated) {
            reading.status = STATUS_CALIBRATION_PENDING;
            reading.isValid = true;
            snprintf(reading.message, sizeof(reading.message), "CALIBRATION PENDING");
            return reading;
        }

        // Standard temperature-compensated TDS formula (assuming nominal 25C)
        // TDS = (133.42 * V^3 - 255.86 * V^2 + 857.39 * V) * 0.5 * kFactor
        float v = reading.reconstructedVoltage;
        float tds = (133.42f * v * v * v - 255.86f * v * v + 857.39f * v) * 0.5f * _kFactor;
        if (tds < 0.0f) tds = 0.0f;

        reading.calibratedValue = tds;
        reading.isValid = true;

        if (tds > 500.0f) {
            reading.status = STATUS_WARNING;
            snprintf(reading.message, sizeof(reading.message), "HIGH TDS (%.0f ppm)", tds);
        } else {
            reading.status = STATUS_OK;
            snprintf(reading.message, sizeof(reading.message), "NORMAL (%.0f ppm)", tds);
        }

        return reading;
    }

private:
    uint8_t _pin;
    bool _enabled;
    bool _isCalibrated;
    float _kFactor;
};
