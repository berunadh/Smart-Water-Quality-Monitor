#pragma once

#include <math.h>
#include <stdint.h>
#ifdef ARDUINO
#include "../config.h"
#else
#ifndef HAZARD_PH_MIN
#define HAZARD_PH_MIN               5.00f
#define HAZARD_PH_MAX               9.50f
#define HAZARD_TDS_MAX_PPM          700.0f
#define HAZARD_TURB_MAX_NTU         150.0f
#define HAZARD_WQS_CAP              20.0f
#define WQS_WEIGHT_TDS              0.40f
#define WQS_WEIGHT_PH               0.35f
#define WQS_WEIGHT_TURB             0.25f
enum WaterStatusCode {
    WATER_STATUS_FAULT    = -1,
    WATER_STATUS_HAZARD   = 0,
    WATER_STATUS_POOR     = 1,
    WATER_STATUS_MODERATE = 2,
    WATER_STATUS_GOOD     = 3,
    WATER_STATUS_NOMINAL  = 4,
    WATER_STATUS_DEMO     = 99
};
#endif
#endif

/**
 * ============================================================================
 * PURE C++ WATER QUALITY SCORE (WQS) & CRITICAL HAZARD OVERRIDE ENGINE
 * ============================================================================
 * Weighted Sub-Index Formula (Section 7):
 *   WQS = 0.40 * q_TDS + 0.35 * q_pH + 0.25 * q_Turb
 *
 * Sub-index normalization [0, 100] anchored on documented BIS 10500:2012, WHO,
 * and Section 8 Critical Hazard limits:
 *   - q_pH  : 100 at pH 7.0; 80 at BIS acceptable edges (6.5 / 8.5);
 *             0 at critical limits (<= 5.0 or >= 9.5)
 *   - q_TDS : 100 at 0 ppm; 80 at BIS acceptable limit (500 ppm);
 *             0 at critical limit (>= 700 ppm)
 *   - q_Turb: 100 at 0 NTU; 80 at BIS acceptable limit (1.0 NTU);
 *             50 at WHO/BIS permissible limit (5.0 NTU);
 *             0 at critical limit (>= 150.0 NTU)
 *
 * Critical Hazard Override (Section 8):
 *   Valid readings satisfying ANY of:
 *     - pH < 5.0 or pH > 9.5
 *     - TDS > 700 ppm
 *     - Turbidity > 150 NTU
 *     - Turbidity outside valid calibration range (healthy probe)
 *   immediately set waterStatus = 0 (HAZARD) and cap WQS <= 20.0.
 *   Disconnected, missing, or hardware-faulty sensors NEVER trigger hazard.
 *
 * DISCLAIMER: Software-generated WQS is preliminary operational screening
 * only and is NOT regulatory certification or proof of potable safety.
 * ============================================================================
 */

struct WqsEvaluationResult {
    bool wqsValid;
    float wqs;
    float qPh;
    float qTds;
    float qTurb;
    bool criticalHazard;
    bool hazardPh;
    bool hazardTds;
    bool hazardTurb;
    bool hazardTurbRange;
    int waterStatusCode; // 4=Nominal, 3=Accept, 2=Marginal, 1=Degraded, 0=Hazard, -1=Fault, 99=Demo
};

inline float clamp0100(float val) {
    if (isnan(val) || isinf(val)) return 0.0f;
    if (val < 0.0f) return 0.0f;
    if (val > 100.0f) return 100.0f;
    return val;
}

inline float computeSubIndexPh(float ph) {
    if (isnan(ph) || isinf(ph)) return 0.0f;
    if (ph <= 5.0f || ph >= 9.5f) return 0.0f;
    if (ph >= 6.5f && ph <= 8.5f) {
        if (ph <= 7.0f) {
            return clamp0100(80.0f + ((ph - 6.5f) / 0.5f) * 20.0f);
        }
        return clamp0100(100.0f - ((ph - 7.0f) / 1.5f) * 20.0f);
    }
    if (ph < 6.5f) {
        return clamp0100(((ph - 5.0f) / 1.5f) * 80.0f);
    }
    return clamp0100(((9.5f - ph) / 1.0f) * 80.0f);
}

inline float computeSubIndexTds(float tdsPpm) {
    if (isnan(tdsPpm) || isinf(tdsPpm) || tdsPpm < 0.0f) return 0.0f;
    if (tdsPpm >= 700.0f) return 0.0f;
    if (tdsPpm <= 500.0f) {
        return clamp0100(100.0f - (tdsPpm / 500.0f) * 20.0f);
    }
    return clamp0100(((700.0f - tdsPpm) / 200.0f) * 80.0f);
}

inline float computeSubIndexTurbidity(float turbNtu) {
    if (isnan(turbNtu) || isinf(turbNtu) || turbNtu < 0.0f) return 0.0f;
    if (turbNtu >= 150.0f) return 0.0f;
    if (turbNtu <= 1.0f) {
        return clamp0100(100.0f - turbNtu * 20.0f);
    }
    if (turbNtu <= 5.0f) {
        return clamp0100(80.0f - ((turbNtu - 1.0f) / 4.0f) * 30.0f);
    }
    return clamp0100(((150.0f - turbNtu) / 145.0f) * 50.0f);
}

inline const char* getWaterStatusName(int statusCode) {
    switch (statusCode) {
        case WATER_STATUS_NOMINAL:  return "NOMINAL";
        case WATER_STATUS_GOOD:     return "GOOD";
        case WATER_STATUS_MODERATE: return "MODERATE";
        case WATER_STATUS_POOR:     return "POOR";
        case WATER_STATUS_HAZARD:   return "HAZARD";
        case WATER_STATUS_DEMO:     return "DEMO";
        case WATER_STATUS_FAULT:
        default:                    return "FAULT";
    }
}

inline WqsEvaluationResult evaluateWaterQualityAndHazards(
    bool phValid,
    float phVal,
    bool turbValid,
    float turbVal,
    bool turbOutOfCalRange,
    bool tdsValid,
    float tdsVal,
    bool anyHardwareFault,
    bool demoMode = false
) {
    WqsEvaluationResult res;
    res.wqsValid = false;
    res.wqs = NAN;
    res.qPh = NAN;
    res.qTds = NAN;
    res.qTurb = NAN;
    res.criticalHazard = false;
    res.hazardPh = false;
    res.hazardTds = false;
    res.hazardTurb = false;
    res.hazardTurbRange = false;
    res.waterStatusCode = WATER_STATUS_FAULT;

    // 1. Evaluate Critical Hazard Override ONLY on valid measurements (or healthy out-of-range turbidity)
    if (phValid && !isnan(phVal) && !isinf(phVal)) {
        if (phVal < HAZARD_PH_MIN || phVal > HAZARD_PH_MAX) {
            res.hazardPh = true;
        }
    }
    if (tdsValid && !isnan(tdsVal) && !isinf(tdsVal)) {
        if (tdsVal > HAZARD_TDS_MAX_PPM) {
            res.hazardTds = true;
        }
    }
    if (turbValid && !isnan(turbVal) && !isinf(turbVal)) {
        if (turbVal > HAZARD_TURB_MAX_NTU) {
            res.hazardTurb = true;
        }
    }
    if (turbOutOfCalRange) {
        res.hazardTurbRange = true;
    }

    res.criticalHazard = res.hazardPh || res.hazardTds || res.hazardTurb || res.hazardTurbRange;

    // 2. Compute WQS ONLY when all three measurements are valid & finite
    if (phValid && turbValid && tdsValid &&
        !isnan(phVal) && !isinf(phVal) &&
        !isnan(turbVal) && !isinf(turbVal) &&
        !isnan(tdsVal) && !isinf(tdsVal)) {
        res.qPh = computeSubIndexPh(phVal);
        res.qTds = computeSubIndexTds(tdsVal);
        res.qTurb = computeSubIndexTurbidity(turbVal);
        float wqs = (WQS_WEIGHT_TDS * res.qTds) +
                    (WQS_WEIGHT_PH * res.qPh) +
                    (WQS_WEIGHT_TURB * res.qTurb);
        if (!isnan(wqs) && !isinf(wqs)) {
            res.wqs = clamp0100(wqs);
            res.wqsValid = true;
        }
    }

    // 3. Apply Critical Hazard Override immediately
    if (res.criticalHazard) {
        res.waterStatusCode = WATER_STATUS_HAZARD;
        if (res.wqsValid && res.wqs > HAZARD_WQS_CAP) {
            res.wqs = HAZARD_WQS_CAP;
        }
        return res;
    }

    if (demoMode) {
        res.waterStatusCode = WATER_STATUS_DEMO;
        return res;
    }

    if (anyHardwareFault || !res.wqsValid) {
        res.waterStatusCode = WATER_STATUS_FAULT;
        return res;
    }

    // 4. Map WQS [0, 100] to documented operational status codes
    if (res.wqs >= 80.0f) {
        res.waterStatusCode = WATER_STATUS_NOMINAL;
    } else if (res.wqs >= 60.0f) {
        res.waterStatusCode = WATER_STATUS_GOOD;
    } else if (res.wqs >= 40.0f) {
        res.waterStatusCode = WATER_STATUS_MODERATE;
    } else if (res.wqs > 20.0f) {
        res.waterStatusCode = WATER_STATUS_POOR;
    } else {
        res.waterStatusCode = WATER_STATUS_HAZARD;
    }

    return res;
}
