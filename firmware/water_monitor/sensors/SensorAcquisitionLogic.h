#pragma once

#include <math.h>
#include <stdint.h>

/** Pure acquisition helpers: conversion is deliberately independent of calibration. */
inline float adcMilliVoltsToVolts(float millivolts) {
    return (isnan(millivolts) || isinf(millivolts) || millivolts < 0.0f) ? NAN : millivolts / 1000.0f;
}

inline float reconstructDividerVoltage(float adcVolts, float multiplier) {
    return (isnan(adcVolts) || isinf(adcVolts) || adcVolts < 0.0f || multiplier <= 0.0f)
        ? NAN : adcVolts * multiplier;
}

/**
 * Chemical/optical signals can be genuinely stable for minutes.  This detector
 * is opt-in so a stable voltage is never confused with a disconnected sensor.
 */
inline bool updateAnalogStuckDetector(
    bool enabled,
    float currentVolts,
    float& previousVolts,
    uint8_t& consecutiveCount,
    float minimumDeltaVolts = 0.0005f,
    uint8_t requiredConsecutive = 15
) {
    if (!enabled || isnan(currentVolts) || isinf(currentVolts)) {
        previousVolts = -1.0f;
        consecutiveCount = 0;
        return false;
    }
    if (previousVolts >= 0.0f && fabsf(currentVolts - previousVolts) < minimumDeltaVolts) {
        if (consecutiveCount < 255) consecutiveCount++;
    } else {
        consecutiveCount = 0;
        previousVolts = currentVolts;
    }
    return consecutiveCount > requiredConsecutive;
}
