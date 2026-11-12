#pragma once

#include <math.h>
#include <stdint.h>

/**
 * ============================================================================
 * PURE C++ TURBIDITY SENSOR LOGIC (HARDWARE-INDEPENDENT & TESTABLE)
 * ============================================================================
 * Optical transmission turbidity probe:
 * - Higher voltage corresponds to lower turbidity (vClearMv > vStdMv).
 * - Does NOT assume visually clear water equals exactly 0.0 NTU.
 * - Rejects readings outside the supported measured calibration range.
 * ============================================================================
 */

struct TurbidityCal {
    bool isValid;
    bool isBoardMv;
    float vClearMv;
    float ntuClear;
    float vStdMv;
    float ntuStd;
    float vMinMv;
    float vMaxMv;
    float ntuMin;
    float ntuMax;
};

struct TurbidityEvalResult {
    bool isValid;
    bool outOfCalRange;
    float ntu;
};

/**
 * Piecewise-continuous provisional NTU estimate anchored on hardware board
 * voltage observations (reconstructed V_board = V_ADC * 2.50):
 * - Below roVolts (down to minVolts): smooth ramp [floorNtu, roNtu].
 * - Between roVolts (0.939V -> 0.50 NTU) and tapVolts (1.484V -> 3.20 NTU):
 *   continuous linear interpolation.
 * - Above tapVolts (up to maxVolts): continuous slope extension clamped to
 *   [0, maxEstimate].
 * - Rejects NaN, Inf, or out-of-range/disconnected voltages safely.
 */
inline TurbidityEvalResult evaluateReferenceTurbidityProvisionalModel(
    float boardVolts,
    float roVolts = 0.939f,
    float roNtu = 0.50f,
    float tapVolts = 1.484f,
    float tapNtu = 3.20f,
    float minVolts = 0.20f,
    float maxVolts = 5.50f,
    float floorNtu = 0.15f,
    float maxEstimate = 100.0f
) {
    TurbidityEvalResult res = {false, false, NAN};
    if (isnan(boardVolts) || isinf(boardVolts) ||
        isnan(roVolts) || isinf(roVolts) ||
        isnan(tapVolts) || isinf(tapVolts) ||
        tapVolts <= roVolts || roVolts <= minVolts ||
        boardVolts < minVolts || boardVolts > maxVolts) {
        res.outOfCalRange = true;
        return res;
    }

    float ntu = NAN;
    if (boardVolts < roVolts) {
        float frac = (boardVolts - minVolts) / (roVolts - minVolts);
        ntu = floorNtu + frac * (roNtu - floorNtu);
    } else {
        float slope = (tapNtu - roNtu) / (tapVolts - roVolts);
        ntu = roNtu + slope * (boardVolts - roVolts);
    }

    if (isnan(ntu) || isinf(ntu)) {
        return res;
    }
    if (ntu < 0.0f) ntu = 0.0f;
    if (ntu > maxEstimate) ntu = maxEstimate;
    res.isValid = true;
    res.ntu = ntu;
    return res;
}

/**
 * Exponential moving average noise filter for turbidity NTU output.
 * Initializes cleanly on the first valid sample and guards non-finite inputs.
 */
inline float applyTurbidityEmaFilter(
    float rawNtu,
    bool& hasPrev,
    float& prevFilteredNtu,
    float alpha = 0.25f
) {
    if (isnan(rawNtu) || isinf(rawNtu)) {
        return NAN;
    }
    if (rawNtu < 0.0f) rawNtu = 0.0f;
    if (alpha < 0.0f) alpha = 0.0f;
    if (alpha > 1.0f) alpha = 1.0f;

    if (!hasPrev || isnan(prevFilteredNtu) || isinf(prevFilteredNtu)) {
        prevFilteredNtu = rawNtu;
        hasPrev = true;
    } else {
        prevFilteredNtu = prevFilteredNtu + alpha * (rawNtu - prevFilteredNtu);
    }
    return prevFilteredNtu;
}

/** Legacy DFRobot SEN0189 quadratic retained only for reference compatibility. */
inline TurbidityEvalResult evaluateSen0189ProvisionalModel(
    float boardVolts,
    float minVolts = 0.0f,
    float maxVolts = 4.5f,
    float maxEstimate = 3000.0f
) {
    TurbidityEvalResult res = {false, false, NAN};
    if (isnan(boardVolts) || isinf(boardVolts) || boardVolts < minVolts || boardVolts > maxVolts) {
        res.outOfCalRange = true;
        return res;
    }
    float estimate = -1120.4f * boardVolts * boardVolts + 5742.3f * boardVolts - 4352.9f;
    if (isnan(estimate) || isinf(estimate)) return res;
    if (estimate < 0.0f) estimate = 0.0f;
    if (estimate > maxEstimate) estimate = maxEstimate;
    res.isValid = true;
    res.ntu = estimate;
    return res;
}

inline TurbidityCal buildTurbidityCalibration(
    float vClearMv,
    float ntuClear,
    float vStdMv,
    float ntuStd,
    float vMinMv,
    float vMaxMv,
    float ntuMin,
    float ntuMax,
    bool isBoardMv = true
) {
    TurbidityCal cal;
    cal.isValid = false;
    cal.isBoardMv = isBoardMv;
    cal.vClearMv = vClearMv;
    cal.ntuClear = ntuClear;
    cal.vStdMv = vStdMv;
    cal.ntuStd = ntuStd;
    cal.vMinMv = vMinMv;
    cal.vMaxMv = vMaxMv;
    cal.ntuMin = ntuMin;
    cal.ntuMax = ntuMax;

    if (isnan(vClearMv) || isinf(vClearMv) ||
        isnan(ntuClear) || isinf(ntuClear) ||
        isnan(vStdMv) || isinf(vStdMv) ||
        isnan(ntuStd) || isinf(ntuStd)) {
        return cal;
    }

    float minClearBoundMv = isBoardMv ? 500.0f : 200.0f;
    float maxBoundMv = isBoardMv ? 5000.0f : 3050.0f;
    if (vClearMv < minClearBoundMv || vClearMv > maxBoundMv || vStdMv <= 0.0f || vStdMv >= vClearMv) {
        return cal;
    }

    // Strict optical monotonicity: voltage decreases as NTU increases
    if ((vClearMv - vStdMv) < 150.0f || ntuClear < 0.0f || ntuStd <= ntuClear) {
        return cal;
    }

    // Default supported voltage window to measured calibration span if explicit bounds were omitted
    if (isnan(vMinMv) || isinf(vMinMv)) {
        cal.vMinMv = vStdMv;
    }
    if (isnan(vMaxMv) || isinf(vMaxMv)) {
        cal.vMaxMv = vClearMv;
    }
    if (isnan(ntuMin) || isinf(ntuMin)) {
        cal.ntuMin = ntuClear;
    }
    if (isnan(ntuMax) || isinf(ntuMax)) {
        cal.ntuMax = ntuStd;
    }

    if (cal.vMinMv >= cal.vMaxMv || cal.ntuMin < 0.0f || cal.ntuMax < cal.ntuStd) {
        return cal;
    }

    cal.isValid = true;
    return cal;
}

inline TurbidityEvalResult evaluateTurbidityReading(float measMv, const TurbidityCal& cal) {
    TurbidityEvalResult res;
    res.isValid = false;
    res.outOfCalRange = false;
    res.ntu = NAN;

    if (!cal.isValid || isnan(measMv) || isinf(measMv)) {
        return res;
    }

    // Reject voltages outside the verified calibration range (triggers Section 8 hazard override)
    if (measMv < cal.vMinMv || measMv > cal.vMaxMv) {
        res.outOfCalRange = true;
        return res;
    }

    float ntu = cal.ntuClear + ((cal.vClearMv - measMv) / (cal.vClearMv - cal.vStdMv)) * (cal.ntuStd - cal.ntuClear);
    if (isnan(ntu) || isinf(ntu) || ntu < cal.ntuMin || ntu > cal.ntuMax) {
        res.outOfCalRange = true;
        return res;
    }

    res.isValid = true;
    res.ntu = ntu;
    return res;
}
