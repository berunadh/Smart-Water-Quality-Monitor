#pragma once

#include <Arduino.h>
#include <math.h>
#include "../config.h"

/**
 * ============================================================================
 * SENSOR BASE CLASS & DATA STRUCTURES
 * ============================================================================
 * Defines the common sensor acquisition contract, trimmed-mean filtering,
 * electrical boundary checks, stabilization sampling, and standardized
 * reading payload.
 * ============================================================================
 */

enum SensorStatus {
    STATUS_OK,                    // Valid, calibrated measurement within safe range
    STATUS_CALIBRATION_PENDING,   // Voltage is valid, but physical calibration is required
    STATUS_WARNING,               // Parameter is outside optimal safe water thresholds
    STATUS_CRITICAL,              // Parameter is at an alarming/dangerous level
    STATUS_OVER_RANGE,            // Electrical hazard: ADC reading exceeds safe limit (>3.05V)
    STATUS_DISCONNECTED,          // Probe is disconnected or reading open-circuit ground
    STATUS_STUCK,                 // Sensor output frozen without natural ADC variance
    STATUS_UNAVAILABLE,           // Sensor hardware not present (e.g. Future TDS)
    STATUS_ERROR                  // General sensor hardware fault
};

struct SensorReading {
    float rawAdc;                 // Filtered 12-bit ADC value (0 - 4095)
    float adcVoltage;             // Measured voltage at ESP32 GPIO (0.0V - 3.3V)
    float reconstructedVoltage;   // Voltage before divider (V_ADC * 2.50)
    float calibratedValue;        // Final engineering unit (pH, NTU, ppm), or NAN
    SensorStatus status;          // Current diagnostic status
    bool isValid;                 // True only if electrically and physically trustworthy
    char message[32];             // Human-readable status description
};

class SensorBase {
public:
    virtual ~SensorBase() = default;
    virtual void begin() = 0;
    virtual SensorReading read() = 0;
    virtual bool isAvailable() const = 0;
    virtual bool isCalibrated() const = 0;

    /**
     * Converts raw 12-bit ADC integer to volts (0.0 to 3.3V).
     */
    float rawToAdcVoltage(float raw) const {
        return (raw / ESP32_ADC_MAX_RAW) * ESP32_ADC_VREF;
    }

    /**
     * Reconstructs the voltage output of the sensor signal conditioning board
     * based on the calibrated resistor divider ratio:
     * V_sensor = V_ADC * ((R1 + R2) / R2)
     */
    float adcToReconstructedVoltage(float vAdc) const {
        return vAdc * VOLTAGE_RECONSTRUCT_FACTOR;
    }

    /**
     * Validates whether the voltage at the GPIO pin is within safe limits.
     * Flags electrical hazard if ADC is saturating near 3.3V.
     */
    bool isOverRange(float raw, float vAdc) const {
        return (raw >= ADC_OVER_RANGE_RAW || vAdc >= ADC_OVER_RANGE_VOLTS);
    }

protected:
    /**
     * Takes multiple ADC samples, sorts them, trims upper and lower 20%
     * to eliminate line noise spikes, and returns the arithmetic mean.
     */
    float sampleAdcTrimmed(uint8_t pin, uint8_t samples, uint8_t delayMs) {
        if (samples < 5) samples = 5;
        if (samples > 50) samples = 50;

        uint16_t buffer[50];
        for (uint8_t i = 0; i < samples; i++) {
            buffer[i] = analogRead(pin);
            if (delayMs > 0) delay(delayMs);
        }

        // Insertion sort
        for (uint8_t i = 1; i < samples; i++) {
            uint16_t key = buffer[i];
            int8_t j = i - 1;
            while (j >= 0 && buffer[j] > key) {
                buffer[j + 1] = buffer[j];
                j--;
            }
            buffer[j + 1] = key;
        }

        // Trim 20% from both ends
        uint8_t trimCount = (samples * ADC_TRIM_PERCENT) / 100;
        if (trimCount < 1) trimCount = 1;

        uint32_t sum = 0;
        uint8_t validCount = 0;
        for (uint8_t i = trimCount; i < (samples - trimCount); i++) {
            sum += buffer[i];
            validCount++;
        }

        if (validCount == 0) return (float)buffer[samples / 2];
        return (float)sum / (float)validCount;
    }

    /**
     * Collects multiple oversampled readings over a stabilization window,
     * calculating the average reconstructed board voltage and sample standard deviation.
     * Used by calibration routines to verify measurement stability before acceptance.
     */
    bool sampleStableVoltage(uint8_t pin, uint8_t sampleCount, uint16_t delayMs, float& avgVoltage, float& stdDev) {
        if (sampleCount < 5) sampleCount = 5;
        if (sampleCount > 50) sampleCount = 50;

        float voltages[50];
        float sum = 0.0f;

        for (uint8_t i = 0; i < sampleCount; i++) {
            float raw = sampleAdcTrimmed(pin, 15, 2);
            float vadc = rawToAdcVoltage(raw);
            voltages[i] = adcToReconstructedVoltage(vadc);
            sum += voltages[i];
            if (delayMs > 0) delay(delayMs);
        }

        avgVoltage = sum / (float)sampleCount;

        float varSum = 0.0f;
        for (uint8_t i = 0; i < sampleCount; i++) {
            float diff = voltages[i] - avgVoltage;
            varSum += diff * diff;
        }
        stdDev = sqrt(varSum / (float)sampleCount);
        return true;
    }
};
