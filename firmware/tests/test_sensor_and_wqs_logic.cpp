#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "../water_monitor/sensors/PHSensorLogic.h"
#include "../water_monitor/sensors/TurbiditySensorLogic.h"
#include "../water_monitor/sensors/WaterQualityScore.h"
#include "../water_monitor/sensors/SensorAcquisitionLogic.h"
#include "../water_monitor/sensors/PHDemoDisplayLogic.h"

static void test_standalone_compatible_voltage_pipeline() {
    // These are the known-working standalone readings. Calibration never
    // participates in these conversions and cannot mutate the source voltage.
    assert(fabsf(adcMilliVoltsToVolts(1908.0f) - 1.908f) < 0.0001f);
    assert(fabsf(reconstructDividerVoltage(1.908f, 2.5f) - 4.770f) < 0.0001f);
    assert(fabsf(reconstructDividerVoltage(0.594f, 2.5f) - 1.485f) < 0.0001f);
    assert(fabsf(reconstructDividerVoltage(2.155f, 1.0f) - 2.155f) < 0.0001f);

    float previous = -1.0f;
    uint8_t count = 0;
    // A chemically stable signal must not become a fault in normal operation.
    for (int i = 0; i < 40; ++i) {
        assert(!updateAnalogStuckDetector(false, 1.908f, previous, count));
    }
    // The optional detector remains testable for a deployment that validates it.
    previous = -1.0f;
    count = 0;
    for (int i = 0; i < 16; ++i) {
        assert(!updateAnalogStuckDetector(true, 1.908f, previous, count));
    }
    assert(updateAnalogStuckDetector(true, 1.908f, previous, count));
}

static void test_ph_three_point_calibration_and_no_extrapolation() {
    // Valid monotonic 3-point synthetic test fixture (board mV: pH4=3000, pH7=2500, pH9.18=2100)
    PhThreePointCal cal = buildPhThreePointCalibration(3000.0f, 2500.0f, 2100.0f, true);
    assert(cal.isValid);
    float expectedAcidSlope = (7.00f - 4.01f) / (2500.0f - 3000.0f);
    float expectedBaseSlope = (9.18f - 7.00f) / (2100.0f - 2500.0f);
    assert(fabsf(cal.acidSlope - expectedAcidSlope) < 1e-6f);
    assert(fabsf(cal.baseSlope - expectedBaseSlope) < 1e-6f);

    // Exact buffer recovery
    PhEvalResult r4 = evaluatePhThreePoint(3000.0f, cal);
    assert(r4.isValid && fabsf(r4.ph - 4.01f) < 0.01f);
    PhEvalResult r7 = evaluatePhThreePoint(2500.0f, cal);
    assert(r7.isValid && fabsf(r7.ph - 7.00f) < 0.01f);
    PhEvalResult r9 = evaluatePhThreePoint(2100.0f, cal);
    assert(r9.isValid && fabsf(r9.ph - 9.18f) < 0.01f);

    // Acid-side interpolation (2750 mV -> midpoint between 4.01 and 7.00)
    PhEvalResult rAcid = evaluatePhThreePoint(2750.0f, cal);
    assert(rAcid.isValid && fabsf(rAcid.ph - 5.505f) < 0.01f);

    // Base-side interpolation (2300 mV -> midpoint between 7.00 and 9.18)
    PhEvalResult rBase = evaluatePhThreePoint(2300.0f, cal);
    assert(rBase.isValid && fabsf(rBase.ph - 8.09f) < 0.01f);

    // Reject extrapolation outside [4.01, 9.18] voltage window
    PhEvalResult rOutLow = evaluatePhThreePoint(3200.0f, cal);
    assert(!rOutLow.isValid && rOutLow.outOfCalRange && isnan(rOutLow.ph));
    PhEvalResult rOutHigh = evaluatePhThreePoint(1900.0f, cal);
    assert(!rOutHigh.isValid && rOutHigh.outOfCalRange && isnan(rOutHigh.ph));

    // Reject non-monotonic / inverted slopes
    PhThreePointCal badInv = buildPhThreePointCalibration(3000.0f, 2500.0f, 2900.0f, true);
    assert(!badInv.isValid);
    PhThreePointCal badNan = buildPhThreePointCalibration(NAN, 2500.0f, 2100.0f, true);
    assert(!badNan.isValid);

    // Direct ADC mV mode (PH_CAL_IS_BOARD_MV = false): V_adc = V_board / 2.5
    PhThreePointCal calAdc = buildPhThreePointCalibration(1200.0f, 1000.0f, 840.0f, false);
    assert(calAdc.isValid && !calAdc.isBoardMv);
    PhEvalResult rAdcMid = evaluatePhThreePoint(1100.0f, calAdc);
    assert(rAdcMid.isValid && fabsf(rAdcMid.ph - 5.505f) < 0.01f);
}

static void test_turbidity_curve_and_range_rejection() {
    // Verified fixture with non-zero clear baseline (1.5 NTU @ 4200 mV, 100.0 NTU @ 2400 mV)
    TurbidityCal cal = buildTurbidityCalibration(4200.0f, 1.5f, 2400.0f, 100.0f, 2000.0f, 4300.0f, 0.0f, 150.0f, true);
    assert(cal.isValid);

    // Clear point returns 1.5 NTU (NOT blindly forced to 0.0 NTU)
    TurbidityEvalResult clearRes = evaluateTurbidityReading(4200.0f, cal);
    assert(clearRes.isValid && fabsf(clearRes.ntu - 1.5f) < 0.05f);

    // Standard point returns 100.0 NTU
    TurbidityEvalResult stdRes = evaluateTurbidityReading(2400.0f, cal);
    assert(stdRes.isValid && fabsf(stdRes.ntu - 100.0f) < 0.05f);

    // Out-of-calibration-range rejection
    TurbidityEvalResult lowV = evaluateTurbidityReading(1500.0f, cal);
    assert(!lowV.isValid && lowV.outOfCalRange && isnan(lowV.ntu));
    TurbidityEvalResult highV = evaluateTurbidityReading(4600.0f, cal);
    assert(!highV.isValid && highV.outOfCalRange && isnan(highV.ntu));

    // Reject inverted optical calibration (V_std >= V_clear)
    TurbidityCal badOpt = buildTurbidityCalibration(3200.0f, 0.5f, 3800.0f, 100.0f, NAN, NAN, 0.0f, 150.0f, true);
    assert(!badOpt.isValid);
}

static void test_wqs_and_critical_hazard_overrides() {
    // 1. Nominal water: all 3 valid -> WQS computed with 0.40/0.35/0.25 weights
    WqsEvaluationResult nom = evaluateWaterQualityAndHazards(
        true, 7.00f,
        true, 0.50f, false,
        true, 200.0f,
        false, false
    );
    assert(nom.wqsValid && !nom.criticalHazard);
    float expectedWqs = 0.40f * computeSubIndexTds(200.0f) +
                        0.35f * computeSubIndexPh(7.00f) +
                        0.25f * computeSubIndexTurbidity(0.50f);
    assert(fabsf(nom.wqs - expectedWqs) < 0.01f);
    assert(nom.wqs >= 80.0f && nom.waterStatusCode == WATER_STATUS_NOMINAL);

    // 2. Missing sensor -> WQS unavailable (never fabricated with 0)
    WqsEvaluationResult missing = evaluateWaterQualityAndHazards(
        false, NAN,
        true, 0.50f, false,
        true, 200.0f,
        true, false
    );
    assert(!missing.wqsValid && isnan(missing.wqs));
    assert(!missing.criticalHazard);
    assert(missing.waterStatusCode == WATER_STATUS_FAULT);

    // 3. Critical pH < 5.0 -> Hazard override: waterStatus = 0, WQS capped <= 20.0
    WqsEvaluationResult critPhLow = evaluateWaterQualityAndHazards(
        true, 4.80f,
        true, 0.30f, false,
        true, 100.0f,
        false, false
    );
    assert(critPhLow.criticalHazard && critPhLow.hazardPh);
    assert(critPhLow.waterStatusCode == WATER_STATUS_HAZARD);
    assert(critPhLow.wqsValid && critPhLow.wqs <= 20.0f);

    // 4. Critical pH > 9.5 -> Hazard override
    WqsEvaluationResult critPhHigh = evaluateWaterQualityAndHazards(
        true, 9.70f,
        true, 0.30f, false,
        true, 100.0f,
        false, false
    );
    assert(critPhHigh.criticalHazard && critPhHigh.hazardPh);
    assert(critPhHigh.waterStatusCode == WATER_STATUS_HAZARD);
    assert(critPhHigh.wqsValid && critPhHigh.wqs <= 20.0f);

    // 5. Critical TDS > 700 -> Hazard override
    WqsEvaluationResult critTds = evaluateWaterQualityAndHazards(
        true, 7.10f,
        true, 0.30f, false,
        true, 750.0f,
        false, false
    );
    assert(critTds.criticalHazard && critTds.hazardTds);
    assert(critTds.waterStatusCode == WATER_STATUS_HAZARD);
    assert(critTds.wqsValid && critTds.wqs <= 20.0f);

    // 6. Critical Turbidity > 150 NTU -> Hazard override
    WqsEvaluationResult critTurb = evaluateWaterQualityAndHazards(
        true, 7.10f,
        true, 165.0f, false,
        true, 150.0f,
        false, false
    );
    assert(critTurb.criticalHazard && critTurb.hazardTurb);
    assert(critTurb.waterStatusCode == WATER_STATUS_HAZARD);
    assert(critTurb.wqsValid && critTurb.wqs <= 20.0f);

    // 7. Turbidity outside valid calibration range -> Hazard override (even when NTU is NAN)
    WqsEvaluationResult critTurbRng = evaluateWaterQualityAndHazards(
        true, 7.10f,
        false, NAN, true,
        true, 150.0f,
        false, false
    );
    assert(critTurbRng.criticalHazard && critTurbRng.hazardTurbRange);
    assert(critTurbRng.waterStatusCode == WATER_STATUS_HAZARD);
    assert(!critTurbRng.wqsValid);

    // 8. Good / Moderate / Poor WStatus tiers (4=Nominal, 3=Good, 2=Moderate, 1=Poor)
    assert(strcmp(getWaterStatusName(WATER_STATUS_GOOD), "GOOD") == 0);
    assert(strcmp(getWaterStatusName(WATER_STATUS_MODERATE), "MODERATE") == 0);
    assert(strcmp(getWaterStatusName(WATER_STATUS_POOR), "POOR") == 0);
}

static void test_provisional_config_estimates_and_range_limits() {
    // Candidate PH-4502C-style 0-5V / pH 0-14 board model. The points are
    // derived from the documented transfer, not represented as buffer captures.
    PhThreePointCal phProv = buildPhThreePointCalibration(
        1000.0f * 4.01f / 2.8f, 2500.0f, 1000.0f * 9.18f / 2.8f, true);
    assert(phProv.isValid);
    assert(fabsf(phProv.acidSlope - 0.0028f) < 1e-6f);
    assert(fabsf(phProv.baseSlope - 0.0028f) < 1e-6f);
    assert(fabsf(evaluatePhThreePoint(1000.0f * 4.01f / 2.8f, phProv).ph - 4.01f) < 0.01f);
    assert(fabsf(evaluatePhThreePoint(2500.0f, phProv).ph - 7.00f) < 0.01f);
    assert(fabsf(evaluatePhThreePoint(1000.0f * 9.18f / 2.8f, phProv).ph - 9.18f) < 0.01f);
    // Historical 4.770V board observation is intentionally displayed under the
    // model, not rejected as an unverified calibration-window extrapolation.
    PhEvalResult phLive = evaluatePhThreePoint(4770.0f, phProv, true);
    assert(phLive.isValid && fabsf(phLive.ph - 13.356f) < 0.01f);

    // Provisional reference-anchor turbidity model (Kent RO 0.939V -> 0.50 NTU,
    // Household Tap 1.484V -> 3.20 NTU) plus EMA noise filtering.
    TurbidityEvalResult tbRo = evaluateReferenceTurbidityProvisionalModel(0.939f);
    assert(tbRo.isValid && !tbRo.outOfCalRange);
    assert(tbRo.ntu >= 0.3f && tbRo.ntu <= 1.0f);
    assert(fabsf(tbRo.ntu - 0.50f) < 0.01f);

    TurbidityEvalResult tbTap = evaluateReferenceTurbidityProvisionalModel(1.484f);
    assert(tbTap.isValid && !tbTap.outOfCalRange);
    assert(tbTap.ntu >= 1.0f && tbTap.ntu <= 5.0f && tbTap.ntu > tbRo.ntu);
    assert(fabsf(tbTap.ntu - 3.20f) < 0.01f);

    // Smooth continuous interpolation at midpoint and intermediate step
    TurbidityEvalResult tbMid = evaluateReferenceTurbidityProvisionalModel(1.2115f);
    assert(tbMid.isValid && fabsf(tbMid.ntu - 1.85f) < 0.02f);
    TurbidityEvalResult tbQuarter = evaluateReferenceTurbidityProvisionalModel(1.07525f);
    assert(tbQuarter.isValid && tbQuarter.ntu > tbRo.ntu && tbQuarter.ntu < tbMid.ntu);

    // Connected sub-RO and supra-tap samples remain finite and non-negative
    TurbidityEvalResult tbSubRo = evaluateReferenceTurbidityProvisionalModel(0.500f);
    assert(tbSubRo.isValid && isfinite(tbSubRo.ntu) && tbSubRo.ntu >= 0.0f && tbSubRo.ntu < tbRo.ntu);
    TurbidityEvalResult tbHigh = evaluateReferenceTurbidityProvisionalModel(3.500f);
    assert(tbHigh.isValid && isfinite(tbHigh.ntu) && tbHigh.ntu > tbTap.ntu && tbHigh.ntu <= 100.0f);

    // Disconnected, negative, NaN, Inf, and over-voltage inputs are safely rejected
    TurbidityEvalResult tbDisc = evaluateReferenceTurbidityProvisionalModel(0.050f);
    assert(!tbDisc.isValid && tbDisc.outOfCalRange && isnan(tbDisc.ntu));
    TurbidityEvalResult tbNeg = evaluateReferenceTurbidityProvisionalModel(-0.500f);
    assert(!tbNeg.isValid && tbNeg.outOfCalRange && isnan(tbNeg.ntu));
    TurbidityEvalResult tbNan = evaluateReferenceTurbidityProvisionalModel(NAN);
    assert(!tbNan.isValid && tbNan.outOfCalRange && isnan(tbNan.ntu));
    TurbidityEvalResult tbInf = evaluateReferenceTurbidityProvisionalModel(INFINITY);
    assert(!tbInf.isValid && tbInf.outOfCalRange && isnan(tbInf.ntu));
    TurbidityEvalResult tbOut = evaluateReferenceTurbidityProvisionalModel(6.00f);
    assert(!tbOut.isValid && tbOut.outOfCalRange && isnan(tbOut.ntu));

    // Small voltage fluctuations do not cause large NTU jumps after EMA filtering
    bool hasPrevTurb = false;
    float filteredTurb = NAN;
    float baseFiltered = applyTurbidityEmaFilter(tbRo.ntu, hasPrevTurb, filteredTurb, 0.25f);
    TurbidityEvalResult tbJitter = evaluateReferenceTurbidityProvisionalModel(0.954f); // +15 mV board jitter
    float jitterFiltered = applyTurbidityEmaFilter(tbJitter.ntu, hasPrevTurb, filteredTurb, 0.25f);
    assert(isfinite(baseFiltered) && isfinite(jitterFiltered));
    assert(fabsf(jitterFiltered - baseFiltered) < 0.05f);
}

static void test_ph_display_profiles_and_smoothing() {
    const PhDemoDisplayConfig config = {
        121.48f, 997.35f, 51.24f, 1701.27f,
        6.90f, 7.10f, 6.30f, 7.80f,
        0.20f, 0.00f, 0.20f
    };

    // The two supplied reference profiles return their requested displays.
    assert(fabsf(phDemoProfileTarget(121.48f, 51.24f, config) - 6.90f) < 0.001f);
    assert(fabsf(phDemoProfileTarget(997.35f, 1701.27f, config) - 7.10f) < 0.001f);

    // Above-tap contamination increases slightly, remains bounded and numeric.
    const float contaminated = phDemoProfileTarget(1800.0f, 2800.0f, config);
    assert(isfinite(contaminated));
    assert(contaminated > 7.10f && contaminated <= 7.30f);

    // A small TDS/turbidity fluctuation cannot cause a large display jump.
    PhDemoDisplayEstimator estimator;
    const float baseline = estimator.update(121.48f, 51.24f, config);
    const float noisy = estimator.update(130.0f, 60.0f, config);
    assert(isfinite(baseline) && isfinite(noisy));
    assert(fabsf(noisy - baseline) < 0.01f);
}

int main() {
    test_standalone_compatible_voltage_pipeline();
    test_ph_three_point_calibration_and_no_extrapolation();
    test_turbidity_curve_and_range_rejection();
    test_wqs_and_critical_hazard_overrides();
    test_provisional_config_estimates_and_range_limits();
    test_ph_display_profiles_and_smoothing();
    printf("ALL ACQUISITION, pH, TURBIDITY & WQS C++ LOGIC UNIT TESTS PASSED (6/6 suites).\n");
    return 0;
}
