#pragma once

#include <Arduino.h>
#include <Preferences.h>
#include "SensorBase.h"
#include "PHSensorLogic.h"

/**
 * ============================================================================
 * pH SENSOR DRIVER (E201-C ELECTRODE + SIGNAL CONDITIONING BOARD)
 * ============================================================================
 * Pin: GPIO34 (ADC1_CH6 - Input Only)
 * Circuit: P pin -> 15kΩ -> GPIO34 -> 10kΩ -> GND
 * Reconstructed V_board = V_ADC * 2.500
 *
 * Three-Point Calibration Mathematics (pH 4.01, pH 7.00, pH 9.18):
 *   acidSlope = (7.00 - 4.01) / (PH_CAL_7_MV - PH_CAL_4_MV)
 *   baseSlope = (9.18 - 7.00) / (PH_CAL_9_MV - PH_CAL_7_MV)
 *   Transition point: pH 7.00 (PH_CAL_7_MV)
 *
 * - Distinguishes ADC pin millivolts vs reconstructed sensor-board millivolts.
 * - Validates slope direction (monotonicity) and magnitude.
 * - Rejects extrapolation outside verified calibration range [4.01, 9.18].
 * - Preserves existing valid ESP32 NVS records in namespace 'watersens'.
 * ============================================================================
 */

class PHSensor : public SensorBase {
public:
    PHSensor(uint8_t pin = PIN_PH_ADC)
        : _pin(pin),
          _isCalibrated(false),
          _isProvisional(false),
          _isThreePoint(false),
          _vPh7(0.0f),
          _vPh4(0.0f),
          _vPh9(0.0f),
          _slope(0.0f),
          _intercept(0.0f),
          _stuckCounter(0),
          _lastVoltage(-1.0f) {
        memset(&_threePtCal, 0, sizeof(_threePtCal));
        _threePtCal.isValid = false;
        snprintf(_nvsDiag, sizeof(_nvsDiag), "Not checked yet");
    }

    void begin() override {
        pinMode(_pin, INPUT);
        loadOrApplyFinalCalibration();
    }

    bool isAvailable() const override { return true; }
    // True ONLY when experimentally verified via NVS/buffers (provisional config.h estimates return false)
    bool isCalibrated() const override { return _isCalibrated && !_isProvisional; }
    bool isProvisional() const { return _isCalibrated && _isProvisional; }
    bool hasCalibrationModel() const { return _isCalibrated; }
    bool isThreePoint() const { return _isThreePoint; }

    float getVPh7() const { return _vPh7; }
    float getVPh4() const { return _vPh4; }
    float getVPh9() const { return _vPh9; }
    float getSlope() const { return _slope; }
    float getAcidSlope() const { return _isThreePoint ? _threePtCal.acidSlope : (_slope / 1000.0f); }
    float getBaseSlope() const { return _isThreePoint ? _threePtCal.baseSlope : (_slope / 1000.0f); }
    float getIntercept() const { return _intercept; }
    const PhThreePointCal& getThreePointCal() const { return _threePtCal; }
    const char* getNvsDiagnostic() const { return _nvsDiag; }

    bool acquireCalibrationSample(
        float& outRawAdc,
        float& outAdcMv,
        float& outBoardMv,
        float& outStdDevAdcMv,
        float& outStdDevBoardMv
    ) {
        return sampleStableChannelMilliVolts(
            _pin, 30, 80, VOLTAGE_RECONSTRUCT_FACTOR,
            outRawAdc, outAdcMv, outBoardMv, outStdDevAdcMv, outStdDevBoardMv
        );
    }

    /**
     * Applies 3-point calibration (in mV) and optionally persists to NVS
     * without overwriting identical existing records.
     * When provisional == true, keeps NVS untouched until physical buffer confirmation.
     */
    bool setThreePointCalibration(
        float v4Mv,
        float v7Mv,
        float v9Mv,
        bool isBoardMv = PH_CAL_IS_BOARD_MV,
        bool saveToNvs = true,
        bool provisional = false
    ) {
        PhThreePointCal cal = buildPhThreePointCalibration(v4Mv, v7Mv, v9Mv, isBoardMv);
        if (!cal.isValid) {
            snprintf(_nvsDiag, sizeof(_nvsDiag), "3-point pH constants invalid or non-monotonic");
            Serial.printf("[CAL-pH] ERROR: Invalid 3-point voltages (V4=%.1fmV, V7=%.1fmV, V9=%.1fmV, board=%d)\n",
                          v4Mv, v7Mv, v9Mv, isBoardMv ? 1 : 0);
            return false;
        }

        _threePtCal = cal;
        _isThreePoint = true;
        _isCalibrated = true;
        _isProvisional = provisional;
        _vPh4 = v4Mv / 1000.0f;
        _vPh7 = v7Mv / 1000.0f;
        _vPh9 = v9Mv / 1000.0f;
        _slope = cal.acidSlope * 1000.0f;
        _intercept = 7.00f - (_slope * _vPh7);

        if (provisional) {
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "PROVISIONAL RAM curve (V4=%.0f V7=%.0f V9=%.0f mV); NVS untouched",
                     v4Mv, v7Mv, v9Mv);
            Serial.printf("[CAL-pH] Loaded PROVISIONAL config estimate in RAM: %s\n", _nvsDiag);
            return true;
        }

        if (saveToNvs) {
            return saveCalibration();
        }
        return true;
    }

    bool saveCalibration() {
        if (_isProvisional) {
            return false;
        }
        return saveThreePointIfChanged();
    }

    void resetCalibration() {
        _isCalibrated = false;
        _isProvisional = false;
        _isThreePoint = false;
        _vPh7 = 0.0f;
        _vPh4 = 0.0f;
        _vPh9 = 0.0f;
        _slope = 0.0f;
        _intercept = 0.0f;
        memset(&_threePtCal, 0, sizeof(_threePtCal));
        _threePtCal.isValid = false;

        Preferences prefs;
        if (prefs.begin("watersens", false)) {
            prefs.remove("ph_cal");
            prefs.remove("ph_3pt");
            prefs.remove("ph_bmv");
            prefs.remove("ph_v4_mv");
            prefs.remove("ph_v7_mv");
            prefs.remove("ph_v9_mv");
            prefs.remove("ph_acid_sl");
            prefs.remove("ph_base_sl");
            prefs.remove("ph_v7");
            prefs.remove("ph_v4");
            prefs.remove("ph_slope");
            prefs.remove("ph_inter");
            prefs.end();
        }
        snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' OK; pH calibration reset");
    }

    /**
     * Checks NVS FIRST so user-saved calibration is NEVER overwritten by config.h;
     * falls back to config.h constants only if NVS has no valid pH calibration.
     */
    void loadOrApplyFinalCalibration() {
        loadCalibration();
        if (_isCalibrated && !_isProvisional) {
            return;
        }

        bool configSupplied = !isnan((float)PH_CAL_4_MV) &&
                              !isnan((float)PH_CAL_7_MV) &&
                              !isnan((float)PH_CAL_9_MV);

        if (configSupplied) {
            setThreePointCalibration(
                (float)PH_CAL_4_MV,
                (float)PH_CAL_7_MV,
                (float)PH_CAL_9_MV,
                PH_CAL_IS_BOARD_MV,
                !PH_CAL_IS_PROVISIONAL,
                PH_CAL_IS_PROVISIONAL
            );
        }
    }

    void loadCalibration() {
        Preferences prefs;
        if (!prefs.begin("watersens", true)) {
            // Initialize namespace non-destructively in RW mode so future opens succeed
            if (prefs.begin("watersens", false)) {
                prefs.end();
                snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' initialized; awaiting PH_CAL_4/7/9_MV");
            } else {
                snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' NVS open FAILED");
            }
            _isCalibrated = false;
            _isThreePoint = false;
            Serial.printf("[CAL-NVS] pH: %s\n", _nvsDiag);
            return;
        }

        // 1. Check 3-point NVS record first
        if (prefs.getBool("ph_3pt", false)) {
            float v4 = prefs.getFloat("ph_v4_mv", NAN);
            float v7 = prefs.getFloat("ph_v7_mv", NAN);
            float v9 = prefs.getFloat("ph_v9_mv", NAN);
            bool bmv = prefs.getBool("ph_bmv", true);
            prefs.end();

            PhThreePointCal cal = buildPhThreePointCalibration(v4, v7, v9, bmv);
            if (cal.isValid) {
                _threePtCal = cal;
                _isThreePoint = true;
                _isCalibrated = true;
                _isProvisional = false;
                _vPh4 = v4 / 1000.0f;
                _vPh7 = v7 / 1000.0f;
                _vPh9 = v9 / 1000.0f;
                _slope = cal.acidSlope * 1000.0f;
                _intercept = 7.00f - (_slope * _vPh7);
                snprintf(_nvsDiag, sizeof(_nvsDiag),
                         "Namespace 'watersens' OK; 3pt VALID (acid=%.5f base=%.5f pH/mV)",
                         cal.acidSlope, cal.baseSlope);
                Serial.printf("[CAL] Loaded 3-point pH calibration from NVS: %s\n", _nvsDiag);
                return;
            }
            // Fall through to check legacy 2-point record if 3-point record was corrupt
            if (!prefs.begin("watersens", true)) {
                _isCalibrated = false;
                return;
            }
        }

        // 2. Preserve existing valid legacy 2-point NVS record if present
        bool hasKey = prefs.isKey("ph_cal");
        bool cal = hasKey ? prefs.getBool("ph_cal", false) : false;
        if (!hasKey || !cal) {
            _isCalibrated = false;
            _isThreePoint = false;
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "Namespace 'watersens' OK; %s (awaiting PH_CAL_4/7/9_MV)",
                     hasKey ? "ph_cal=false" : "no ph_cal key");
            Serial.printf("[CAL-NVS] pH: %s\n", _nvsDiag);
            prefs.end();
            return;
        }

        bool hasV7 = prefs.isKey("ph_v7");
        bool hasV4 = prefs.isKey("ph_v4");
        bool hasSl = prefs.isKey("ph_slope");
        bool hasIn = prefs.isKey("ph_inter");
        float v7 = prefs.getFloat("ph_v7", 0.0f);
        float v4 = prefs.getFloat("ph_v4", 0.0f);
        float sl = prefs.getFloat("ph_slope", 0.0f);
        float in = prefs.getFloat("ph_inter", 0.0f);
        prefs.end();

        if (hasV7 && hasV4 && hasSl && hasIn &&
            !isnan(v7) && !isnan(v4) && !isnan(sl) && !isnan(in) &&
            v7 > 0.1f && v4 > 0.1f && fabsf(sl) >= 0.50f && fabsf(sl) <= 12.00f) {
            _vPh7 = v7;
            _vPh4 = v4;
            _slope = sl;
            _intercept = in;
            _isCalibrated = true;
            _isProvisional = false;
            _isThreePoint = false;
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "Namespace 'watersens' OK; legacy 2pt VALID (V7=%.3fV V4=%.3fV Slope=%.3f)",
                     _vPh7, _vPh4, _slope);
            Serial.printf("[CAL] Loaded legacy pH calibration from NVS: %s\n", _nvsDiag);
        } else {
            _isCalibrated = false;
            _isThreePoint = false;
            snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' OK; NVS pH keys invalid");
            Serial.printf("[CAL-NVS] pH: %s\n", _nvsDiag);
        }
    }

    bool verifyNvsReadback() const {
        if (!_isThreePoint || !_threePtCal.isValid) return false;
        Preferences prefs;
        if (!prefs.begin("watersens", true)) return false;
        bool ok = prefs.getBool("ph_3pt", false) &&
                  fabsf(prefs.getFloat("ph_v4_mv", -1.0f) - _threePtCal.v4Mv) < 0.01f &&
                  fabsf(prefs.getFloat("ph_v7_mv", -1.0f) - _threePtCal.v7Mv) < 0.01f &&
                  fabsf(prefs.getFloat("ph_v9_mv", -1.0f) - _threePtCal.v9Mv) < 0.01f &&
                  fabsf(prefs.getFloat("ph_acid_sl", 0.0f) - _threePtCal.acidSlope) < 1e-6f &&
                  fabsf(prefs.getFloat("ph_base_sl", 0.0f) - _threePtCal.baseSlope) < 1e-6f;
        prefs.end();
        return ok;
    }

    SensorReading read() override {
        SensorReading reading;
        memset(&reading, 0, sizeof(reading));
        reading.calibratedValue = NAN;

        // 1. Oversample ADC with factory-calibrated mV + 2.5x divider reconstruction
        sampleChannelTrimmedMilliVolts(_pin, ADC_OVERSAMPLE_SAMPLES, ADC_SAMPLE_DELAY_MS,
                                       reading.rawAdc, reading.adcVoltage);
        reading.reconstructedVoltage = adcToReconstructedVoltage(reading.adcVoltage);

        // 2. Electrical Over-Range Safety Check
        if (isOverRange(reading.rawAdc, reading.adcVoltage)) {
            reading.status = STATUS_OVER_RANGE;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "ADC OVER-RANGE (>3.05V)");
            return reading;
        }

        // 3. Disconnected / Open-Circuit Check (guards against ESP32 0-count ~140mV mV intercept)
        if (reading.rawAdc < ADC_DISCONNECTED_RAW || reading.adcVoltage < ADC_DISCONNECTED_VOLTS) {
            reading.status = STATUS_DISCONNECTED;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "DISCONNECTED/0V");
            return reading;
        }

        // A stable pH voltage is normal. This is disabled by default so it
        // cannot turn the measured 4-19mV sample variation into a false fault.
        if (isStableVoltageFault(reading.adcVoltage, _lastVoltage, _stuckCounter)) {
            reading.status = STATUS_STUCK;
            reading.isValid = false;
            snprintf(reading.message, sizeof(reading.message), "STUCK READING");
            return reading;
        }

        // 5. Calibration check: never fabricate pH without verified constants/NVS
        if (!_isCalibrated) {
            reading.status = STATUS_CALIBRATION_PENDING;
            reading.isValid = true; // Signal board voltage is electrically healthy
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "CAL CONSTANTS NEEDED");
            return reading;
        }

        // A nominal PH-4502C-style curve would map the observed 4.770V board
        // output to ~13.36 pH. It is unchanged for the RO and tap references,
        // so it is not a defensible physical pH estimate. Preserve voltage and
        // verified NVS calibration behaviour, but never publish that false value.
        if (_isProvisional && PH_REJECT_SUSPECT_PROVISIONAL_RESPONSE) {
            reading.status = STATUS_CALIBRATION_PENDING;
            reading.isValid = true;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "PH RESPONSE SUSPECT");
            return reading;
        }

        // 6. Compute calibrated pH using finalized 3-point model (or legacy 2-point NVS)
        float ph = NAN;
        if (_isThreePoint) {
            float measMv = _threePtCal.isBoardMv
                ? (reading.reconstructedVoltage * 1000.0f)
                : (reading.adcVoltage * 1000.0f);
            PhEvalResult eval = evaluatePhThreePoint(measMv, _threePtCal, _isProvisional);
            if (!eval.isValid) {
                reading.status = eval.outOfCalRange ? STATUS_OUT_OF_CAL_RANGE : STATUS_ERROR;
                reading.isValid = false;
                reading.calibratedValue = NAN;
                snprintf(reading.message, sizeof(reading.message),
                         eval.outOfCalRange
                             ? (_isProvisional ? "PROV pH OUT OF RNG" : "pH OUT OF CAL RANGE")
                             : "pH EVAL ERROR");
                return reading;
            }
            ph = eval.ph;
        } else {
            ph = (_slope * reading.reconstructedVoltage) + _intercept;
            if (isnan(ph) || isinf(ph) || ph < 0.0f || ph > 14.0f) {
                reading.status = STATUS_ERROR;
                reading.isValid = false;
                reading.calibratedValue = NAN;
                snprintf(reading.message, sizeof(reading.message), "IMPLAUSIBLE pH");
                return reading;
            }
        }

        reading.calibratedValue = ph;
        reading.isValid = true;

        if (ph < HAZARD_PH_MIN || ph > HAZARD_PH_MAX) {
            reading.status = STATUS_CRITICAL;
            snprintf(reading.message, sizeof(reading.message), "HAZARD pH (%.2f)", ph);
        } else if (ph < THRESHOLD_PH_WARNING_MIN || ph > THRESHOLD_PH_WARNING_MAX) {
            reading.status = STATUS_WARNING;
            if (_isProvisional) {
                snprintf(reading.message, sizeof(reading.message), "%.2f pH (PR-WARN)", ph);
            } else {
                snprintf(reading.message, sizeof(reading.message), "pH OUT OF RANGE");
            }
        } else {
            reading.status = STATUS_OK;
            if (_isProvisional) {
                snprintf(reading.message, sizeof(reading.message), "%.2f pH (PROV)", ph);
            } else {
                snprintf(reading.message, sizeof(reading.message), "NORMAL (%.2f)", ph);
            }
        }

        return reading;
    }

private:
    uint8_t _pin;
    bool _isCalibrated;
    bool _isProvisional;
    bool _isThreePoint;
    float _vPh7;
    float _vPh4;
    float _vPh9;
    float _slope;
    float _intercept;
    PhThreePointCal _threePtCal;
    uint8_t _stuckCounter;
    float _lastVoltage;
    char _nvsDiag[144];

    bool saveThreePointIfChanged() {
        if (verifyNvsReadback()) {
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "Namespace 'watersens' OK; 3pt VERIFIED (acid=%.5f base=%.5f)",
                     _threePtCal.acidSlope, _threePtCal.baseSlope);
            return true;
        }

        Preferences prefs;
        if (!prefs.begin("watersens", false)) {
            snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' NVS write FAILED");
            return false;
        }

        prefs.putBool("ph_3pt", true);
        prefs.putBool("ph_cal", true);
        prefs.putBool("ph_bmv", _threePtCal.isBoardMv);
        prefs.putFloat("ph_v4_mv", _threePtCal.v4Mv);
        prefs.putFloat("ph_v7_mv", _threePtCal.v7Mv);
        prefs.putFloat("ph_v9_mv", _threePtCal.v9Mv);
        prefs.putFloat("ph_acid_sl", _threePtCal.acidSlope);
        prefs.putFloat("ph_base_sl", _threePtCal.baseSlope);
        prefs.putFloat("ph_v4", _vPh4);
        prefs.putFloat("ph_v7", _vPh7);
        prefs.putFloat("ph_slope", _slope);
        prefs.putFloat("ph_inter", _intercept);
        prefs.end();

        bool ok = verifyNvsReadback();
        snprintf(_nvsDiag, sizeof(_nvsDiag),
                 ok ? "Namespace 'watersens' OK; 3pt SAVED & VERIFIED"
                    : "Namespace 'watersens' 3pt readback mismatch!");
        return ok;
    }
};
