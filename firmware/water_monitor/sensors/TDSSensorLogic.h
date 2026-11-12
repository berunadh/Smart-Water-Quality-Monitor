#pragma once

#include <math.h>
#include <stdint.h>

/**
 * ============================================================================
 * PURE C++ TDS SENSOR LOGIC (HARDWARE-INDEPENDENT & TESTABLE)
 * ============================================================================
 * Contains pure mathematical conversions, dry/disconnected/valid state
 * classification, single-point calibration proposal validation, and live
 * verification tolerance evaluation for the GPIO35 Direct 3.3V TDS sensor.
 *
 * Electrical & Physical Limitations:
 * - Polynomial assumes ~25 deg C nominal solution temperature (no temp sensor).
 * - Assumes DFRobot SEN0244-compatible cubic response curve; single-point
 *   calibration does NOT prove curve accuracy across the full 0-3000 ppm range.
 * - Voltage alone cannot universally separate a dry probe from ultra-pure/
 *   distilled water if both yield the same board baseline or sit inside the
 *   ESP32 ADC1 11dB bottom deadzone (~0-2 raw counts).
 * ============================================================================
 */

struct TdsConfigBounds {
    float disconnectedVolts;
    float overRangeVolts;
    float overRangeRaw;
    float zeroDeadbandRaw;
    float dryMarginVolts;
    float dryMaxBaselineVolts;
    float calMinVolts;
    float calMaxVolts;
    float calMaxStdDevVolts;
    float calMinPpm;
    float calMaxPpm;
    float kFactorMin;
    float kFactorMax;
    float maxPlausiblePpm;
    float verifyTolerancePct;
};

inline TdsConfigBounds makeDefaultTdsBounds() {
    TdsConfigBounds b;
    b.disconnectedVolts = 0.015f;
    b.overRangeVolts = 3.05f;
    b.overRangeRaw = 4000.0f;
    b.zeroDeadbandRaw = 3.0f;
    b.dryMarginVolts = 0.030f;
    b.dryMaxBaselineVolts = 1.000f;
    b.calMinVolts = 0.100f;
    b.calMaxVolts = 2.950f;
    b.calMaxStdDevVolts = 0.050f;
    b.calMinPpm = 10.0f;
    b.calMaxPpm = 3000.0f;
    b.kFactorMin = 0.15f;
    b.kFactorMax = 5.00f;
    b.maxPlausiblePpm = 5000.0f;
    b.verifyTolerancePct = 5.0f;
    return b;
}

/**
 * Applies standard temperature compensation to measured TDS sensor voltage (V):
 *   V_comp = V / (1.0 + 0.02 * (T - 25.0))
 * When no physical temperature sensor is installed, T defaults to 25.0 deg C.
 */
inline float compensateTdsVoltage(float vVolts, float tempC = 25.0f) {
    if (isnan(vVolts) || isinf(vVolts) || vVolts <= 0.0f) {
        return 0.0f;
    }
    if (isnan(tempC) || isinf(tempC)) {
        tempC = 25.0f;
    }
    float compDenom = 1.0f + 0.02f * (tempC - 25.0f);
    if (compDenom <= 0.05f) {
        return 0.0f;
    }
    float vComp = vVolts / compDenom;
    if (isnan(vComp) || isinf(vComp) || vComp <= 0.0f) {
        return 0.0f;
    }
    return vComp;
}

inline float computeTdsRawPolynomialPpm(float vAdc, float tempC = 25.0f) {
    float vComp = compensateTdsVoltage(vAdc, tempC);
    if (vComp <= 0.0f || isnan(vComp) || isinf(vComp)) {
        return 0.0f;
    }
    float poly = 0.5f * (133.42f * vComp * vComp * vComp - 255.86f * vComp * vComp + 857.39f * vComp);
    if (isnan(poly) || isinf(poly) || poly <= 0.0f) {
        return 0.0f;
    }
    return poly;
}

enum TdsSignalClassification {
    TDS_STATE_UNAVAILABLE = 0,
    TDS_STATE_OVER_RANGE,
    TDS_STATE_DISCONNECTED,
    TDS_STATE_DRY_OR_NO_SIGNAL,
    TDS_STATE_STUCK,
    TDS_STATE_CALIBRATION_PENDING,
    TDS_STATE_IMPLAUSIBLE,
    TDS_STATE_VALID_CALIBRATED
};

struct TdsClassificationResult {
    TdsSignalClassification state;
    bool isValid;
    float calibratedPpm;
};

inline TdsClassificationResult classifyTdsSignal(
    bool enabled,
    bool isCalibrated,
    float kFactor,
    float rawAdc,
    float adcVoltage,
    bool hasDryBaseline,
    float dryBaselineVolts,
    bool isStuck,
    const TdsConfigBounds& bounds,
    float tempC = 25.0f,
    bool allowModelWithoutNvsCal = false
) {
    TdsClassificationResult res;
    res.state = TDS_STATE_UNAVAILABLE;
    res.isValid = false;
    res.calibratedPpm = NAN;

    if (!enabled) {
        res.state = TDS_STATE_UNAVAILABLE;
        return res;
    }

    if (isnan(adcVoltage) || isinf(adcVoltage) || rawAdc >= bounds.overRangeRaw || adcVoltage >= bounds.overRangeVolts) {
        res.state = TDS_STATE_OVER_RANGE;
        return res;
    }

    // Genuine near-0V shorted or unwired signal
    if (adcVoltage < bounds.disconnectedVolts) {
        res.state = TDS_STATE_DISCONNECTED;
        return res;
    }

    // ESP32 ADC1 11dB bottom deadzone (0-2 raw counts): analogReadMilliVolts()
    // returns line-fitting intercept (~0.10-0.14V) even at 0V input.
    if (rawAdc < bounds.zeroDeadbandRaw) {
        res.state = TDS_STATE_DRY_OR_NO_SIGNAL;
        return res;
    }

    // Optional hardware-measured dry-air baseline (recorded explicitly via 'tds dry')
    if (hasDryBaseline && adcVoltage <= (dryBaselineVolts + bounds.dryMarginVolts)) {
        res.state = TDS_STATE_DRY_OR_NO_SIGNAL;
        return res;
    }

    if (isStuck) {
        res.state = TDS_STATE_STUCK;
        return res;
    }

    float effectiveK = 0.0f;
    if (isCalibrated && kFactor > 0.0f) {
        effectiveK = kFactor;
    } else if (allowModelWithoutNvsCal) {
        effectiveK = (kFactor > 0.0f) ? kFactor : 1.0f;
    } else {
        res.state = TDS_STATE_CALIBRATION_PENDING;
        res.isValid = true; // Electrically healthy input, awaiting reference calibration
        return res;
    }

    float tds = computeTdsRawPolynomialPpm(adcVoltage, tempC) * effectiveK;
    if (isnan(tds) || isinf(tds) || tds < 0.0f || tds > bounds.maxPlausiblePpm) {
        res.state = TDS_STATE_IMPLAUSIBLE;
        return res;
    }

    res.state = TDS_STATE_VALID_CALIBRATED;
    res.isValid = true;
    res.calibratedPpm = tds;
    return res;
}

enum TdsProposalStatus {
    TDS_PROP_OK = 0,
    TDS_PROP_ERR_DISABLED,
    TDS_PROP_ERR_INVALID_PPM,
    TDS_PROP_ERR_OVER_RANGE,
    TDS_PROP_ERR_DISCONNECTED,
    TDS_PROP_ERR_UNSTABLE,
    TDS_PROP_ERR_VOLTAGE_BOUNDS,
    TDS_PROP_ERR_MATCHES_DRY_BASELINE,
    TDS_PROP_ERR_LOW_POLY,
    TDS_PROP_ERR_KFACTOR_BOUNDS
};

struct TdsProposalEvaluation {
    TdsProposalStatus status;
    bool accepted;
    float rawPolynomialPpm;
    float candidateKFactor;
    bool kFactorDeviationAdvisory;
};

inline TdsProposalEvaluation evaluateTdsCalibrationProposal(
    bool enabled,
    float avgVoltage,
    float stdDev,
    float avgRawAdc,
    float knownTdsPpm,
    bool hasDryBaseline,
    float dryBaselineVolts,
    const TdsConfigBounds& bounds
) {
    TdsProposalEvaluation out;
    out.status = TDS_PROP_ERR_DISABLED;
    out.accepted = false;
    out.rawPolynomialPpm = 0.0f;
    out.candidateKFactor = 0.0f;
    out.kFactorDeviationAdvisory = false;

    if (!enabled) {
        out.status = TDS_PROP_ERR_DISABLED;
        return out;
    }

    if (isnan(knownTdsPpm) || isinf(knownTdsPpm) ||
        knownTdsPpm < bounds.calMinPpm || knownTdsPpm > bounds.calMaxPpm) {
        out.status = TDS_PROP_ERR_INVALID_PPM;
        return out;
    }

    if (isnan(avgVoltage) || isinf(avgVoltage) ||
        avgRawAdc >= bounds.overRangeRaw || avgVoltage >= bounds.overRangeVolts) {
        out.status = TDS_PROP_ERR_OVER_RANGE;
        return out;
    }

    if (avgVoltage < bounds.disconnectedVolts || avgRawAdc < bounds.zeroDeadbandRaw) {
        out.status = TDS_PROP_ERR_DISCONNECTED;
        return out;
    }

    if (isnan(stdDev) || isinf(stdDev) || stdDev > bounds.calMaxStdDevVolts) {
        out.status = TDS_PROP_ERR_UNSTABLE;
        return out;
    }

    if (avgVoltage < bounds.calMinVolts || avgVoltage > bounds.calMaxVolts) {
        out.status = TDS_PROP_ERR_VOLTAGE_BOUNDS;
        return out;
    }

    if (hasDryBaseline && avgVoltage <= (dryBaselineVolts + bounds.dryMarginVolts)) {
        out.status = TDS_PROP_ERR_MATCHES_DRY_BASELINE;
        return out;
    }

    float rawPoly = computeTdsRawPolynomialPpm(avgVoltage);
    out.rawPolynomialPpm = rawPoly;
    if (rawPoly < 5.0f) {
        out.status = TDS_PROP_ERR_LOW_POLY;
        return out;
    }

    float k = knownTdsPpm / rawPoly;
    out.candidateKFactor = k;
    if (isnan(k) || isinf(k) || k < bounds.kFactorMin || k > bounds.kFactorMax) {
        out.status = TDS_PROP_ERR_KFACTOR_BOUNDS;
        return out;
    }

    out.kFactorDeviationAdvisory = (k < 0.50f || k > 2.00f);
    out.status = TDS_PROP_OK;
    out.accepted = true;
    return out;
}

struct TdsVerificationResult {
    bool passed;
    float signedDiffPct;
    float absDiffPct;
    float minAcceptedPpm;
    float maxAcceptedPpm;
};

inline TdsVerificationResult evaluateTdsLiveVerification(
    bool readingValid,
    bool statusIsOk,
    float livePpm,
    float referencePpm,
    float tolerancePct
) {
    TdsVerificationResult res;
    res.passed = false;
    res.signedDiffPct = 0.0f;
    res.absDiffPct = 100.0f;
    res.minAcceptedPpm = referencePpm * (1.0f - (tolerancePct / 100.0f));
    res.maxAcceptedPpm = referencePpm * (1.0f + (tolerancePct / 100.0f));

    if (!readingValid || !statusIsOk || isnan(livePpm) || isinf(livePpm) || referencePpm <= 0.0f) {
        return res;
    }

    res.signedDiffPct = ((livePpm - referencePpm) / referencePpm) * 100.0f;
    res.absDiffPct = fabsf(res.signedDiffPct);
    res.passed = (res.absDiffPct <= tolerancePct);
    return res;
}
