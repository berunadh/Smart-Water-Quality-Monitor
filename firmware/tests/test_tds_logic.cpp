#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "../water_monitor/sensors/TDSSensorLogic.h"

static void test_disconnected_and_deadzone() {
    TdsConfigBounds b = makeDefaultTdsBounds();

    // 1. Genuine < 0.015V shorted/unwired signal -> DISCONNECTED (never valid/calibrated)
    TdsClassificationResult r_disc = classifyTdsSignal(true, true, 1.0f, 10.0f, 0.010f, false, 0.0f, false, b);
    assert(r_disc.state == TDS_STATE_DISCONNECTED);
    assert(!r_disc.isValid);
    assert(isnan(r_disc.calibratedPpm));

    // 2. ESP32 ADC1 11dB 0-count deadzone (rawAdc < 3) even if analogReadMilliVolts returns ~0.142V
    TdsClassificationResult r_dead = classifyTdsSignal(true, true, 1.0f, 0.0f, 0.142f, false, 0.0f, false, b);
    assert(r_dead.state == TDS_STATE_DRY_OR_NO_SIGNAL);
    assert(!r_dead.isValid);
    assert(isnan(r_dead.calibratedPpm));
}

static void test_low_voltage_without_blind_threshold_override() {
    TdsConfigBounds b = makeDefaultTdsBounds();

    // Without recorded dry baseline, a real non-zero signal above 0.015V and >= 3 raw counts
    // is NOT blindly flagged disconnected; before calibration -> CALIBRATION_PENDING
    TdsClassificationResult r_uncal = classifyTdsSignal(true, false, 0.0f, 176.0f, 0.142f, false, 0.0f, false, b);
    assert(r_uncal.state == TDS_STATE_CALIBRATION_PENDING);
    assert(r_uncal.isValid);
    assert(isnan(r_uncal.calibratedPpm));

    // When an explicit dry baseline IS recorded (e.g. 0.142V), dry state <= 0.142 + 0.030 = 0.172V
    // is safely suppressed as DRY_OR_NO_SIGNAL even after calibration
    TdsClassificationResult r_dry = classifyTdsSignal(true, true, 1.0f, 176.0f, 0.142f, true, 0.142f, false, b);
    assert(r_dry.state == TDS_STATE_DRY_OR_NO_SIGNAL);
    assert(!r_dry.isValid);
    assert(isnan(r_dry.calibratedPpm));

    // Above dry baseline + margin -> valid calibrated measurement
    TdsClassificationResult r_wet = classifyTdsSignal(true, true, 1.0f, 2000.0f, 1.782f, true, 0.142f, false, b);
    assert(r_wet.state == TDS_STATE_VALID_CALIBRATED);
    assert(r_wet.isValid);
    assert(r_wet.calibratedPpm > 700.0f && r_wet.calibratedPpm < 770.0f);
}

static void test_over_range_stuck_and_disabled() {
    TdsConfigBounds b = makeDefaultTdsBounds();

    TdsClassificationResult r_over_v = classifyTdsSignal(true, true, 1.0f, 3800.0f, 3.05f, false, 0.0f, false, b);
    assert(r_over_v.state == TDS_STATE_OVER_RANGE);
    assert(!r_over_v.isValid);
    assert(isnan(r_over_v.calibratedPpm));

    TdsClassificationResult r_over_raw = classifyTdsSignal(true, true, 1.0f, 4000.0f, 2.90f, false, 0.0f, false, b);
    assert(r_over_raw.state == TDS_STATE_OVER_RANGE);
    assert(!r_over_raw.isValid);

    TdsClassificationResult r_stuck = classifyTdsSignal(true, true, 1.0f, 1500.0f, 1.25f, false, 0.0f, true, b);
    assert(r_stuck.state == TDS_STATE_STUCK);
    assert(!r_stuck.isValid);
    assert(isnan(r_stuck.calibratedPpm));

    TdsClassificationResult r_off = classifyTdsSignal(false, true, 1.0f, 1500.0f, 1.25f, false, 0.0f, false, b);
    assert(r_off.state == TDS_STATE_UNAVAILABLE);
    assert(!r_off.isValid);
    assert(isnan(r_off.calibratedPpm));
}

static void test_proposal_validation_separated_checks() {
    TdsConfigBounds b = makeDefaultTdsBounds();

    // Valid 342 ppm proposal at 0.94V (k ~ 0.99)
    TdsProposalEvaluation ok = evaluateTdsCalibrationProposal(true, 0.94f, 0.015f, 1100.0f, 342.0f, true, 0.142f, b);
    assert(ok.accepted);
    assert(ok.status == TDS_PROP_OK);
    assert(ok.candidateKFactor > 0.90f && ok.candidateKFactor < 1.10f);
    assert(!ok.kFactorDeviationAdvisory);

    // Unstable sample rejected
    TdsProposalEvaluation unstable = evaluateTdsCalibrationProposal(true, 0.94f, 0.055f, 1100.0f, 342.0f, false, 0.0f, b);
    assert(!unstable.accepted);
    assert(unstable.status == TDS_PROP_ERR_UNSTABLE);

    // Out-of-bounds voltage rejected
    TdsProposalEvaluation highV = evaluateTdsCalibrationProposal(true, 2.98f, 0.010f, 3800.0f, 342.0f, false, 0.0f, b);
    assert(!highV.accepted);
    assert(highV.status == TDS_PROP_ERR_VOLTAGE_BOUNDS);

    // Dry baseline match rejected
    TdsProposalEvaluation dryMatch = evaluateTdsCalibrationProposal(true, 0.150f, 0.010f, 180.0f, 342.0f, true, 0.142f, b);
    assert(!dryMatch.accepted);
    assert(dryMatch.status == TDS_PROP_ERR_MATCHES_DRY_BASELINE);

    // Implausible kFactor rejected (e.g. accidentally typing 700 uS/cm at 0.12V -> rawPoly ~49, k > 5.0)
    TdsProposalEvaluation badK = evaluateTdsCalibrationProposal(true, 0.12f, 0.010f, 140.0f, 342.0f, false, 0.0f, b);
    assert(!badK.accepted);
    assert(badK.status == TDS_PROP_ERR_KFACTOR_BOUNDS);

    // Invalid ppm rejected
    TdsProposalEvaluation badPpm = evaluateTdsCalibrationProposal(true, 1.0f, 0.010f, 1200.0f, 5.0f, false, 0.0f, b);
    assert(!badPpm.accepted);
    assert(badPpm.status == TDS_PROP_ERR_INVALID_PPM);
}

static void test_live_verification_tolerance() {
    // 342 ppm +/- 5% => [324.9, 359.1]
    TdsVerificationResult pass_low = evaluateTdsLiveVerification(true, true, 325.0f, 342.0f, 5.0f);
    assert(pass_low.passed);
    assert(fabsf(pass_low.minAcceptedPpm - 324.9f) < 0.05f);
    assert(fabsf(pass_low.maxAcceptedPpm - 359.1f) < 0.05f);

    TdsVerificationResult pass_high = evaluateTdsLiveVerification(true, true, 359.0f, 342.0f, 5.0f);
    assert(pass_high.passed);

    TdsVerificationResult fail_low = evaluateTdsLiveVerification(true, true, 320.0f, 342.0f, 5.0f);
    assert(!fail_low.passed);

    TdsVerificationResult fail_high = evaluateTdsLiveVerification(true, true, 365.0f, 342.0f, 5.0f);
    assert(!fail_high.passed);

    TdsVerificationResult fail_dry = evaluateTdsLiveVerification(false, false, NAN, 342.0f, 5.0f);
    assert(!fail_dry.passed);
}

static void test_temperature_compensation_and_polynomial_model() {
    // 1. Nominal T=25.0C leaves voltage unchanged
    float vComp25 = compensateTdsVoltage(1.500f, 25.0f);
    assert(fabsf(vComp25 - 1.500f) < 1e-5f);

    // 2. T=30.0C -> V_comp = 1.500 / (1 + 0.02 * 5) = 1.500 / 1.10 = 1.363636...
    float vComp30 = compensateTdsVoltage(1.500f, 30.0f);
    assert(fabsf(vComp30 - (1.500f / 1.10f)) < 1e-5f);

    // 3. T=20.0C -> V_comp = 1.500 / (1 + 0.02 * -5) = 1.500 / 0.90 = 1.666667...
    float vComp20 = compensateTdsVoltage(1.500f, 20.0f);
    assert(fabsf(vComp20 - (1.500f / 0.90f)) < 1e-5f);

    // 4. Exact cubic polynomial check at V=1.500V, T=25C
    float expectedPoly = 0.5f * (133.42f * 1.5f * 1.5f * 1.5f - 255.86f * 1.5f * 1.5f + 857.39f * 1.5f);
    assert(fabsf(computeTdsRawPolynomialPpm(1.500f, 25.0f) - expectedPoly) < 0.01f);

    // 5. Invalid inputs never return NaN/negative from polynomial helper
    assert(computeTdsRawPolynomialPpm(NAN, 25.0f) == 0.0f);
    assert(computeTdsRawPolynomialPpm(INFINITY, 25.0f) == 0.0f);
    assert(computeTdsRawPolynomialPpm(-0.5f, 25.0f) == 0.0f);

    // 6. Polynomial model active without manual NVS calibration still rejects dry probe!
    TdsConfigBounds b = makeDefaultTdsBounds();
    TdsClassificationResult dryModel = classifyTdsSignal(true, false, 1.0f, 1.0f, 0.142f, false, 0.0f, false, b, 25.0f, true);
    assert(dryModel.state == TDS_STATE_DRY_OR_NO_SIGNAL);
    assert(!dryModel.isValid);
    assert(isnan(dryModel.calibratedPpm));

    TdsClassificationResult wetModel = classifyTdsSignal(true, false, 1.0f, 1800.0f, 1.500f, false, 0.0f, false, b, 25.0f, true);
    assert(wetModel.state == TDS_STATE_VALID_CALIBRATED);
    assert(wetModel.isValid);
    assert(fabsf(wetModel.calibratedPpm - expectedPoly) < 0.1f);
}

int main() {
    test_disconnected_and_deadzone();
    test_low_voltage_without_blind_threshold_override();
    test_over_range_stuck_and_disabled();
    test_proposal_validation_separated_checks();
    test_live_verification_tolerance();
    test_temperature_compensation_and_polynomial_model();
    printf("ALL TDS FIRMWARE C++ LOGIC UNIT TESTS PASSED (6/6 suites).\n");
    return 0;
}
