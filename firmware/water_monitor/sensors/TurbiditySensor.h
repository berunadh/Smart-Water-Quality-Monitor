#pragma once

#include "SensorBase.h"

/**
 * ============================================================================
 * TURBIDITY SENSOR DRIVER (OPTICAL PROBE + RED SIGNAL CONDITIONING BOARD)
 * ============================================================================
 * Pin: GPIO32 (ADC1_CH4)
 * Circuit: OUT pin -> 15kΩ -> GPIO32 -> 10kΩ -> GND
 * Reconstructed V_board = V_ADC * 2.500
 * 
 * Optical Characteristics:
 * - Clear water (0 NTU): Highest light transmission -> High voltage (~4.0 - 4.5V reconstructed)
 * - Turbid water (>50 NTU): Particle scattering blocks transmission -> Voltage drops
 * 
 * Calibration:
 * Generic quadratic curves vary drastically between probe manufacturing batches.
 * This driver supports two-point calibration using standard turbidity solutions
 * (0 NTU clean baseline and known NTU standard). Uncalibrated readings report
 * STATUS_CALIBRATION_PENDING while displaying electrical voltage honestly.
 * ============================================================================
 */

class TurbiditySensor : public SensorBase {
public:
    TurbiditySensor(uint8_t pin = PIN_TURBIDITY_ADC)
        : _pin(pin),
          _isCalibrated(false),
          _vClear(0.0f),
          _vStandard(0.0f),
          _ntuStandard(0.0f),
          _stuckCounter(0),
          _lastVoltage(-1.0f) {}

    void begin() override {
        pinMode(_pin, INPUT);
    }

    bool isAvailable() const override {
        return true;
    }

    bool isCalibrated() const override {
        return _isCalibrated;
    }

    /**
     * Calibrates turbidity response using clear distilled water (0 NTU)
     * and a certified turbidity standard (e.g., 100 NTU or 400 NTU).
     */
    void setCalibration(float vBoardClear, float vBoardStandard, float ntuStandard) {
        if (vBoardClear <= vBoardStandard || ntuStandard <= 0.0f) {
            // Optical sensor voltage MUST decrease with increasing turbidity
            return;
        }
        _vClear = vBoardClear;
        _vStandard = vBoardStandard;
        _ntuStandard = ntuStandard;
        _isCalibrated = true;
    }

    void resetCalibration() {
        _isCalibrated = false;
        _vClear = 0.0f;
        _vStandard = 0.0f;
        _ntuStandard = 0.0f;
    }

    SensorReading read() override {
        SensorReading reading;
        memset(&reading, 0, sizeof(reading));
        reading.calibratedValue = NAN;

        // In Demo Mode, simulate clean municipal tap water (0.8 NTU, ~4.2V board, ~1.68V ADC)
        if (FEATURE_DEMO_MODE) {
            reading.rawAdc = 2085.0f + (float)(random(-10, 11));
            reading.adcVoltage = rawToAdcVoltage(reading.rawAdc);
            reading.reconstructedVoltage = adcToReconstructedVoltage(reading.adcVoltage);
            reading.calibratedValue = 0.85f + ((2085.0f - reading.rawAdc) * 0.05f);
            if (reading.calibratedValue < 0.1f) reading.calibratedValue = 0.1f;
            reading.status = STATUS_OK;
            reading.isValid = true;
            snprintf(reading.message, sizeof(reading.message), "DEMO (0.85 NTU)");
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

        // 3. Disconnected / Probe off check (optical probe powered off gives ~0V)
        if (reading.adcVoltage < ADC_DISCONNECTED_VOLTS) {
            reading.status = STATUS_DISCONNECTED;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "DISCONNECTED/0V");
            return reading;
        }

        // 4. Stuck reading detection
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

        // 5. Calibration check
        if (!_isCalibrated) {
            reading.status = STATUS_CALIBRATION_PENDING;
            reading.isValid = true; // Signal board reading is electrically healthy
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "CALIBRATION PENDING");
            return reading;
        }

        // 6. Compute calibrated turbidity (linear optical attenuation model)
        // NTU = ( (V_clear - V_meas) / (V_clear - V_standard) ) * NTU_standard
        float deltaV = _vClear - reading.reconstructedVoltage;
        if (deltaV < 0.0f) deltaV = 0.0f; // Cleaner than baseline clear water
        
        float ntu = (deltaV / (_vClear - _vStandard)) * _ntuStandard;

        // 7. Sanity bounds check
        if (ntu < 0.0f || ntu > 3000.0f) {
            reading.status = STATUS_ERROR;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "IMPLAUSIBLE NTU (%.0f)", ntu);
            return reading;
        }

        reading.calibratedValue = ntu;
        reading.isValid = true;

        // 8. Water quality threshold classification
        if (ntu >= THRESHOLD_TURB_CRITICAL_NTU) {
            reading.status = STATUS_CRITICAL;
            snprintf(reading.message, sizeof(reading.message), "HIGH TURBIDITY (%.1f)", ntu);
        } else if (ntu >= THRESHOLD_TURB_WARNING_NTU) {
            reading.status = STATUS_WARNING;
            snprintf(reading.message, sizeof(reading.message), "ELEVATED NTU (%.1f)", ntu);
        } else {
            reading.status = STATUS_OK;
            snprintf(reading.message, sizeof(reading.message), "CLEAR (%.1f NTU)", ntu);
        }

        return reading;
    }

private:
    uint8_t _pin;
    bool _isCalibrated;
    float _vClear;
    float _vStandard;
    float _ntuStandard;
    uint8_t _stuckCounter;
    float _lastVoltage;
};
