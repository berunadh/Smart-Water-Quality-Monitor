#pragma once

#include <Arduino.h>
#include <Preferences.h>
#include "SensorBase.h"
#include "TurbiditySensorLogic.h"

/**
 * ============================================================================
 * TURBIDITY SENSOR DRIVER (OPTICAL PROBE + SIGNAL CONDITIONING BOARD)
 * ============================================================================
 * Pin: GPIO32 (ADC1_CH4 - Input Only)
 * Circuit: OUT pin -> 15kΩ -> GPIO32 -> 10kΩ -> GND
 * Reconstructed V_board = V_ADC * 2.500
 *
 * - Validates optical monotonicity (V_clear > V_standard).
 * - Preserves clear-water baseline NTU (never assumes visually clear == 0 NTU).
 * - Rejects readings outside the supported calibration range (triggers Section 8
 *   critical hazard override when healthy probe goes out of calibration range).
 * - Preserves existing valid NVS keys in namespace 'watersens'.
 * ============================================================================
 */

class TurbiditySensor : public SensorBase {
public:
    TurbiditySensor(uint8_t pin = PIN_TURBIDITY_ADC)
        : _pin(pin),
          _isCalibrated(false),
          _isProvisional(false),
          _usingReferenceProvisionalModel(false),
          _hasFilteredNtu(false),
          _filteredNtu(NAN),
          _vClear(0.0f),
          _vStandard(0.0f),
          _ntuStandard(0.0f),
          _stuckCounter(0),
          _lastVoltage(-1.0f) {
        memset(&_cal, 0, sizeof(_cal));
        _cal.isValid = false;
        snprintf(_nvsDiag, sizeof(_nvsDiag), "Not checked yet");
    }

    void begin() override {
        pinMode(_pin, INPUT);
        loadOrApplyFinalCalibration();
    }

    bool isAvailable() const override { return true; }
    // True ONLY when experimentally verified via NVS/standards (provisional estimates return false)
    bool isCalibrated() const override { return _isCalibrated && !_isProvisional; }
    bool isProvisional() const { return _isCalibrated && _isProvisional; }
    bool hasCalibrationModel() const { return _isCalibrated; }

    float getVClear() const { return _vClear; }
    float getVStandard() const { return _vStandard; }
    float getNtuStandard() const { return _ntuStandard; }
    const TurbidityCal& getCalibrationModel() const { return _cal; }
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

    bool setFinalCalibration(
        float vClearMv,
        float ntuClear,
        float vStdMv,
        float ntuStd,
        float vMinMv = NAN,
        float vMaxMv = NAN,
        float ntuMin = NAN,
        float ntuMax = NAN,
        bool isBoardMv = TURB_CAL_IS_BOARD_MV,
        bool saveToNvs = true,
        bool provisional = false
    ) {
        TurbidityCal cal = buildTurbidityCalibration(
            vClearMv, ntuClear, vStdMv, ntuStd,
            vMinMv, vMaxMv, ntuMin, ntuMax, isBoardMv
        );
        if (!cal.isValid) {
            snprintf(_nvsDiag, sizeof(_nvsDiag), "Turbidity constants invalid or non-monotonic");
            return false;
        }

        _cal = cal;
        _isCalibrated = true;
        _isProvisional = provisional;
        _usingReferenceProvisionalModel = false;
        _hasFilteredNtu = false;
        _filteredNtu = NAN;
        _vClear = cal.vClearMv / 1000.0f;
        _vStandard = cal.vStdMv / 1000.0f;
        _ntuStandard = cal.ntuStd;

        if (provisional) {
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "PROVISIONAL RAM curve (Vc=%.0f Vs=%.0f mV); NVS untouched",
                     vClearMv, vStdMv);
            Serial.printf("[CAL-Turb] Loaded PROVISIONAL config estimate in RAM: %s\n", _nvsDiag);
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
        return saveIfChanged();
    }

    void resetCalibration() {
        _isCalibrated = false;
        _isProvisional = false;
        _usingReferenceProvisionalModel = false;
        _hasFilteredNtu = false;
        _filteredNtu = NAN;
        _vClear = 0.0f;
        _vStandard = 0.0f;
        _ntuStandard = 0.0f;
        memset(&_cal, 0, sizeof(_cal));
        _cal.isValid = false;

        Preferences prefs;
        if (prefs.begin("watersens", false)) {
            prefs.remove("tb_cal");
            prefs.remove("tb_vc");
            prefs.remove("tb_vs");
            prefs.remove("tb_ntu");
            prefs.remove("tb_ntu0");
            prefs.remove("tb_vmin");
            prefs.remove("tb_vmax");
            prefs.remove("tb_nmin");
            prefs.remove("tb_nmax");
            prefs.remove("tb_bmv");
            prefs.end();
        }
        snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' OK; Turbidity calibration reset");
    }

    /**
     * Checks NVS FIRST so user-saved calibration is NEVER overwritten by config.h;
     * falls back to config.h constants only if NVS has no valid turbidity calibration.
     */
    void loadOrApplyFinalCalibration() {
        loadCalibration();
        if (_isCalibrated && !_isProvisional) {
            return;
        }

        bool configSupplied = !isnan((float)TURB_CAL_CLEAR_MV) &&
                              !isnan((float)TURB_CAL_CLEAR_NTU) &&
                              !isnan((float)TURB_CAL_STD_MV) &&
                              !isnan((float)TURB_CAL_STD_NTU);

        if (configSupplied) {
            setFinalCalibration(
                (float)TURB_CAL_CLEAR_MV,
                (float)TURB_CAL_CLEAR_NTU,
                (float)TURB_CAL_STD_MV,
                (float)TURB_CAL_STD_NTU,
                (float)TURB_CAL_MIN_MV,
                (float)TURB_CAL_MAX_MV,
                (float)TURB_CAL_MIN_NTU,
                (float)TURB_CAL_MAX_NTU,
                TURB_CAL_IS_BOARD_MV,
                !TURB_CAL_IS_PROVISIONAL,
                TURB_CAL_IS_PROVISIONAL
            );
        } else if (TURB_USE_REFERENCE_PROVISIONAL_MODEL) {
            setReferenceProvisionalModel();
        }
    }

    void loadCalibration() {
        Preferences prefs;
        if (!prefs.begin("watersens", true)) {
            if (prefs.begin("watersens", false)) {
                prefs.end();
                snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' initialized; awaiting TURB_CAL_*");
            } else {
                snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' NVS open FAILED");
            }
            _isCalibrated = false;
            Serial.printf("[CAL-NVS] Turbidity: %s\n", _nvsDiag);
            return;
        }

        bool hasKey = prefs.isKey("tb_cal");
        bool calFlag = hasKey ? prefs.getBool("tb_cal", false) : false;
        if (!hasKey || !calFlag) {
            _isCalibrated = false;
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "Namespace 'watersens' OK; %s (awaiting TURB_CAL_*)",
                     hasKey ? "tb_cal=false" : "no tb_cal key");
            Serial.printf("[CAL-NVS] Turbidity: %s\n", _nvsDiag);
            prefs.end();
            return;
        }

        float vc = prefs.getFloat("tb_vc", NAN);
        float vs = prefs.getFloat("tb_vs", NAN);
        float ntu = prefs.getFloat("tb_ntu", NAN);
        float ntu0 = prefs.getFloat("tb_ntu0", 0.0f);
        float vminMv = prefs.getFloat("tb_vmin", NAN);
        float vmaxMv = prefs.getFloat("tb_vmax", NAN);
        float nmin = prefs.getFloat("tb_nmin", NAN);
        float nmax = prefs.getFloat("tb_nmax", NAN);
        bool bmv = prefs.getBool("tb_bmv", true);
        prefs.end();

        TurbidityCal loaded = buildTurbidityCalibration(
            vc * 1000.0f, ntu0, vs * 1000.0f, ntu,
            vminMv, vmaxMv, nmin, nmax, bmv
        );
        if (loaded.isValid) {
            _cal = loaded;
            _vClear = vc;
            _vStandard = vs;
            _ntuStandard = ntu;
            _isCalibrated = true;
            _isProvisional = false;
            _usingReferenceProvisionalModel = false;
            _hasFilteredNtu = false;
            _filteredNtu = NAN;
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "Namespace 'watersens' OK; tb_cal=true (Vc=%.3fV Vs=%.3fV %.1fNTU VALID)",
                     _vClear, _vStandard, _ntuStandard);
            Serial.printf("[CAL] Loaded Turbidity calibration from NVS: %s\n", _nvsDiag);
        } else {
            _isCalibrated = false;
            snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' OK; tb_cal=true REJECTED");
            Serial.printf("[CAL-NVS] Turbidity: %s\n", _nvsDiag);
        }
    }

    bool verifyNvsReadback() const {
        if (!_cal.isValid) return false;
        Preferences prefs;
        if (!prefs.begin("watersens", true)) return false;
        bool ok = prefs.getBool("tb_cal", false) &&
                  fabsf(prefs.getFloat("tb_vc", 0.0f) - _vClear) < 1e-4f &&
                  fabsf(prefs.getFloat("tb_vs", 0.0f) - _vStandard) < 1e-4f &&
                  fabsf(prefs.getFloat("tb_ntu", 0.0f) - _ntuStandard) < 1e-2f &&
                  fabsf(prefs.getFloat("tb_ntu0", -1.0f) - _cal.ntuClear) < 1e-2f;
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
            _hasFilteredNtu = false;
            _filteredNtu = NAN;
            reading.status = STATUS_OVER_RANGE;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "ADC OVER-RANGE (>3.05V)");
            return reading;
        }

        // 3. Disconnected / Probe off check (guards against ESP32 0-count ~140mV mV intercept)
        if (reading.rawAdc < ADC_DISCONNECTED_RAW || reading.adcVoltage < ADC_DISCONNECTED_VOLTS) {
            _hasFilteredNtu = false;
            _filteredNtu = NAN;
            reading.status = STATUS_DISCONNECTED;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "DISCONNECTED/0V");
            return reading;
        }

        // Stable optical output is not by itself a sensor failure.
        if (isStableVoltageFault(reading.adcVoltage, _lastVoltage, _stuckCounter)) {
            _hasFilteredNtu = false;
            _filteredNtu = NAN;
            reading.status = STATUS_STUCK;
            reading.isValid = false;
            snprintf(reading.message, sizeof(reading.message), "STUCK READING");
            return reading;
        }

        // 5. Calibration check
        if (!_isCalibrated) {
            _hasFilteredNtu = false;
            _filteredNtu = NAN;
            reading.status = STATUS_CALIBRATION_PENDING;
            reading.isValid = true; // Signal board voltage is electrically healthy
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "CAL CONSTANTS NEEDED");
            return reading;
        }

        // 6. Use actual-standard calibration when present, else the provisional
        // reference-anchor NTU model anchored at Kent RO (0.939V) and Tap (1.484V).
        float measMv = _cal.isBoardMv
            ? (reading.reconstructedVoltage * 1000.0f)
            : (reading.adcVoltage * 1000.0f);
        TurbidityEvalResult eval = _usingReferenceProvisionalModel
            ? evaluateReferenceTurbidityProvisionalModel(
                reading.reconstructedVoltage,
                TURB_PROV_RO_BOARD_V,
                TURB_PROV_RO_NTU,
                TURB_PROV_TAP_BOARD_V,
                TURB_PROV_TAP_NTU,
                TURB_PROV_MIN_BOARD_V,
                TURB_PROV_MAX_BOARD_V,
                TURB_PROV_FLOOR_NTU,
                TURB_PROV_MAX_ESTIMATE_NTU
              )
            : evaluateTurbidityReading(measMv, _cal);
        if (!eval.isValid || isnan(eval.ntu) || isinf(eval.ntu)) {
            _hasFilteredNtu = false;
            _filteredNtu = NAN;
            reading.status = eval.outOfCalRange ? STATUS_OUT_OF_CAL_RANGE : STATUS_ERROR;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message),
                     eval.outOfCalRange
                         ? (_isProvisional ? "PROV TB OUT OF RNG" : "OUT OF CAL RANGE")
                         : "TURB EVAL ERROR");
            return reading;
        }

        // 7. Apply EMA smoothing to suppress ADC noise; single filtered NTU value
        // is consumed identically by OLED display and ThingSpeak Field 2.
        float ntu = applyTurbidityEmaFilter(eval.ntu, _hasFilteredNtu, _filteredNtu, TURB_FILTER_ALPHA);
        if (isnan(ntu) || isinf(ntu) || ntu < 0.0f) {
            _hasFilteredNtu = false;
            _filteredNtu = NAN;
            reading.status = STATUS_ERROR;
            reading.isValid = false;
            reading.calibratedValue = NAN;
            snprintf(reading.message, sizeof(reading.message), "TURB FILTER ERROR");
            return reading;
        }
        reading.calibratedValue = ntu;
        reading.isValid = true;

        if (ntu > HAZARD_TURB_MAX_NTU) {
            reading.status = STATUS_CRITICAL;
            snprintf(reading.message, sizeof(reading.message), "HAZARD TURB (%.1f)", ntu);
        } else if (ntu >= THRESHOLD_TURB_CRITICAL_NTU) {
            reading.status = STATUS_CRITICAL;
            snprintf(reading.message, sizeof(reading.message), "HIGH TURB (%.1f)", ntu);
        } else if (ntu >= THRESHOLD_TURB_WARNING_NTU) {
            reading.status = STATUS_WARNING;
            snprintf(reading.message, sizeof(reading.message),
                     _isProvisional ? "%.1f NTU (PR-WARN)" : "ELEVATED NTU (%.1f)", ntu);
        } else {
            reading.status = STATUS_OK;
            snprintf(reading.message, sizeof(reading.message),
                     _isProvisional ? "%.1f NTU (PROV)" : "%.1f NTU", ntu);
        }

        return reading;
    }

private:
    uint8_t _pin;
    bool _isCalibrated;
    bool _isProvisional;
    bool _usingReferenceProvisionalModel;
    bool _hasFilteredNtu;
    float _filteredNtu;
    float _vClear;
    float _vStandard;
    float _ntuStandard;
    TurbidityCal _cal;
    uint8_t _stuckCounter;
    float _lastVoltage;
    char _nvsDiag[144];

    void setReferenceProvisionalModel() {
        _isCalibrated = true;
        _isProvisional = true;
        _usingReferenceProvisionalModel = true;
        _hasFilteredNtu = false;
        _filteredNtu = NAN;
        _vClear = 0.0f;
        _vStandard = 0.0f;
        _ntuStandard = 0.0f;
        memset(&_cal, 0, sizeof(_cal));
        _cal.isValid = false;
        snprintf(_nvsDiag, sizeof(_nvsDiag),
                 "PROVISIONAL 2-ref NTU estimate (RO %.3fV->%.2f, Tap %.3fV->%.2f); NVS untouched",
                 TURB_PROV_RO_BOARD_V, TURB_PROV_RO_NTU, TURB_PROV_TAP_BOARD_V, TURB_PROV_TAP_NTU);
        Serial.printf("[CAL-Turb] Loaded %s\n", _nvsDiag);
    }

    bool saveIfChanged() {
        if (verifyNvsReadback()) {
            snprintf(_nvsDiag, sizeof(_nvsDiag),
                     "Namespace 'watersens' OK; tb_cal=true VERIFIED (Vc=%.3fV Vs=%.3fV)",
                     _vClear, _vStandard);
            return true;
        }

        Preferences prefs;
        if (!prefs.begin("watersens", false)) {
            snprintf(_nvsDiag, sizeof(_nvsDiag), "Namespace 'watersens' NVS write FAILED");
            return false;
        }
        prefs.putBool("tb_cal", true);
        prefs.putFloat("tb_vc", _vClear);
        prefs.putFloat("tb_vs", _vStandard);
        prefs.putFloat("tb_ntu", _ntuStandard);
        prefs.putFloat("tb_ntu0", _cal.ntuClear);
        prefs.putFloat("tb_vmin", _cal.vMinMv);
        prefs.putFloat("tb_vmax", _cal.vMaxMv);
        prefs.putFloat("tb_nmin", _cal.ntuMin);
        prefs.putFloat("tb_nmax", _cal.ntuMax);
        prefs.putBool("tb_bmv", _cal.isBoardMv);
        prefs.end();

        bool ok = verifyNvsReadback();
        snprintf(_nvsDiag, sizeof(_nvsDiag),
                 ok ? "Namespace 'watersens' OK; tb_cal=true SAVED & VERIFIED"
                    : "Namespace 'watersens' tb_cal readback mismatch!");
        return ok;
    }
};
