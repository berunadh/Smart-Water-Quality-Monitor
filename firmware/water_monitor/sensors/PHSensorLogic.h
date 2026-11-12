#pragma once

#include <math.h>
#include <stdint.h>

/**
 * ============================================================================
 * PURE C++ 3-POINT pH SENSOR LOGIC (HARDWARE-INDEPENDENT & TESTABLE)
 * ============================================================================
 * Reference buffers: pH 4.01, pH 7.00, pH 9.18
 *
 * Equations (millivolt domain):
 *   acidSlope = (7.00 - 4.01) / (PH_CAL_7_MV - PH_CAL_4_MV)
 *   baseSlope = (9.18 - 7.00) / (PH_CAL_9_MV - PH_CAL_7_MV)
 *
 * Transition point: PH_CAL_7_MV (pH 7.00)
 * - Acid branch: pH = 7.00 + acidSlope * (measMv - PH_CAL_7_MV)
 * - Base branch: pH = 7.00 + baseSlope * (measMv - PH_CAL_7_MV)
 *
 * Enforces consistent mV units, slope direction/monotonicity, plausible
 * slope magnitudes, and rejects extrapolation beyond the verified [4.01, 9.18]
 * calibration window.
 * ============================================================================
 */

struct PhThreePointCal {
    bool isValid;
    bool isBoardMv;
    float v4Mv;
    float v7Mv;
    float v9Mv;
    float acidSlope;
    float baseSlope;
    float minValidMv;
    float maxValidMv;
};

struct PhEvalResult {
    bool isValid;
    bool outOfCalRange;
    float ph;
};

inline PhThreePointCal buildPhThreePointCalibration(
    float v4Mv,
    float v7Mv,
    float v9Mv,
    bool isBoardMv = true
) {
    PhThreePointCal cal;
    cal.isValid = false;
    cal.isBoardMv = isBoardMv;
    cal.v4Mv = v4Mv;
    cal.v7Mv = v7Mv;
    cal.v9Mv = v9Mv;
    cal.acidSlope = 0.0f;
    cal.baseSlope = 0.0f;
    cal.minValidMv = 0.0f;
    cal.maxValidMv = 0.0f;

    if (isnan(v4Mv) || isinf(v4Mv) ||
        isnan(v7Mv) || isinf(v7Mv) ||
        isnan(v9Mv) || isinf(v9Mv)) {
        return cal;
    }

    float minBoundMv = isBoardMv ? 100.0f : 40.0f;
    float maxBoundMv = isBoardMv ? 4950.0f : 3050.0f;
    if (v4Mv < minBoundMv || v4Mv > maxBoundMv ||
        v7Mv < minBoundMv || v7Mv > maxBoundMv ||
        v9Mv < minBoundMv || v9Mv > maxBoundMv) {
        return cal;
    }

    float dAcid = v7Mv - v4Mv;
    float dBase = v9Mv - v7Mv;
    if (fabsf(dAcid) < 50.0f || fabsf(dBase) < 50.0f) {
        return cal;
    }

    float acidSlope = (7.00f - 4.01f) / dAcid;
    float baseSlope = (9.18f - 7.00f) / dBase;

    // Validate direction (strictly monotonic: both slopes share the same non-zero sign)
    if ((acidSlope * baseSlope) <= 0.0f) {
        return cal;
    }

    // Validate magnitude (0.0005 to 0.025 pH/mV == 0.5 to 25.0 pH/V)
    float absAcid = fabsf(acidSlope);
    float absBase = fabsf(baseSlope);
    if (absAcid < 0.0005f || absAcid > 0.025f || absBase < 0.0005f || absBase > 0.025f) {
        return cal;
    }

    cal.acidSlope = acidSlope;
    cal.baseSlope = baseSlope;
    cal.minValidMv = (v4Mv < v9Mv) ? v4Mv : v9Mv;
    cal.maxValidMv = (v4Mv > v9Mv) ? v4Mv : v9Mv;
    cal.isValid = true;
    return cal;
}

inline PhEvalResult evaluatePhThreePoint(float measMv, const PhThreePointCal& cal, bool allowModelExtrapolation = false) {
    PhEvalResult res;
    res.isValid = false;
    res.outOfCalRange = false;
    res.ph = NAN;

    if (!cal.isValid || isnan(measMv) || isinf(measMv)) {
        return res;
    }

    // Verified calibration never extrapolates. A visibly labelled provisional
    // board model may cover its documented full transfer range instead.
    if (!allowModelExtrapolation && (measMv < cal.minValidMv || measMv > cal.maxValidMv)) {
        res.outOfCalRange = true;
        return res;
    }

    // Piecewise linear interpolation pivoted at pH 7.00 (v7Mv)
    bool onAcidSide = ((measMv - cal.v7Mv) * (cal.v4Mv - cal.v7Mv)) >= 0.0f;
    float slope = onAcidSide ? cal.acidSlope : cal.baseSlope;
    float ph = 7.00f + slope * (measMv - cal.v7Mv);

    float minPh = allowModelExtrapolation ? 0.0f : 4.01f;
    float maxPh = allowModelExtrapolation ? 14.0f : 9.18f;
    if (isnan(ph) || isinf(ph) || ph < minPh - 1e-3f || ph > maxPh + 1e-3f) {
        res.outOfCalRange = true;
        return res;
    }

    // Clamp only tiny float rounding at the applicable bounds.
    if (ph < minPh) ph = minPh;
    if (ph > maxPh) ph = maxPh;

    res.isValid = true;
    res.ph = ph;
    return res;
}
