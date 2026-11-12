/**
 * ============================================================================
 * HYDROSENSE SMART WATER QUALITY MONITOR - ESP32 FIRMWARE
 * ============================================================================
 * Hardware:
 * - MCU: ESP32-D0WD-V3 (ESP32 Dev Module)
 * - pH Sensor: E201-C probe + Green board on GPIO34 (15k/10k divider, 2.5x)
 * - Turbidity: Optical probe + Red board on GPIO32 (15k/10k divider, 2.5x)
 * - TDS Sensor: TDS Meter V1.0 on GPIO35 (Direct 3.3V ADC, 1.0x, no divider)
 * - Display: SSD1306 128x64 OLED on I2C (SDA=21, SCL=22, addr=0x3C)
 * - Buzzer: Audio alert module on GPIO25
 * - Telemetry: ThingSpeak Channel 3570138 (8-field default; optional 5-field)
 * ============================================================================
 */

#include <Preferences.h>
#include "config.h"
#include "secrets.h"
#include "sensors/PHSensor.h"
#include "sensors/PHDemoDisplayLogic.h"
#include "sensors/TurbiditySensor.h"
#include "sensors/TDSSensor.h"
#include "sensors/SensorValidator.h"
#include "display/DisplayManager.h"
#include "alerts/AlertManager.h"
#include "cloud/CloudManager.h"

// ----------------------------------------------------------------------------
// Global Subsystem Instances
// ----------------------------------------------------------------------------
PHSensor         phSensor(PIN_PH_ADC);
TurbiditySensor  turbSensor(PIN_TURBIDITY_ADC);
TDSSensor        tdsSensor(PIN_TDS_ADC);
SensorValidator  sensorValidator;
DisplayManager   displayManager;
AlertManager     alertManager(PIN_BUZZER);
CloudManager     cloudManager;

// ----------------------------------------------------------------------------
// Runtime State
// ----------------------------------------------------------------------------
SensorReading phReading;
SensorReading turbReading;
SensorReading tdsReading;
PhDemoDisplayEstimator phDisplayEstimator;

uint32_t lastSensorSampleMillis = 0;
uint32_t lastSerialLogMillis    = 0;
bool nvsReady = false;

// Guided Serial Calibration Staging State (never saved until validated & confirmed)
struct PhStagingState {
    bool has4 = false, has7 = false, has9 = false;
    float v4Mv = 0.0f, v7Mv = 0.0f, v9Mv = 0.0f;
    bool proposalValid = false;
} phStage;

struct TurbStagingState {
    bool hasClear = false, hasStd = false;
    float vClearMv = 0.0f, ntuClear = 0.0f;
    float vStdMv = 0.0f, ntuStd = 0.0f;
    bool proposalValid = false;
} turbStage;

struct TdsVerifyStagingState {
    bool hasProposal = false;
    float vAdcVolts = 0.0f;
    float rawAdc = 0.0f;
    float refPpm = 0.0f;
    float proposedK = 1.0f;
} tdsStage;

// Forward Declarations
void ensureNvsNamespaceInitialized();
void processSerialCommands();
void printHelpMenu();
void printDiagnostics();
void printCalibrationStatus();
void printDemoStatus();
void printModeStatus();
void printHealthBreakdown(uint16_t hc);
void handlePhCalibrationPoint(float targetPh);
void evaluateAndReportPhProposal();
void handleTurbClearCapture(float knownClearNtu);
void handleTurbStdCapture(float knownStdNtu);
void evaluateAndReportTurbProposal();
void handleTdsVerifyCapture(float knownRefPpm);
bool commitStagedPhCalibration();
bool commitStagedTurbCalibration();
bool commitStagedTdsCalibration();
void applyPhPresentationEstimate();

// ----------------------------------------------------------------------------
// Safe Non-Destructive NVS Initialization (Never Erases Existing Data)
// ----------------------------------------------------------------------------
void ensureNvsNamespaceInitialized() {
    Preferences prefs;
    if (prefs.begin("watersens", true)) {
        nvsReady = true;
        prefs.end();
        Serial.println(F("[NVS] Namespace 'watersens' opened cleanly (existing records preserved)."));
        return;
    }

    if (prefs.begin("watersens", false)) {
        prefs.end();
        if (prefs.begin("watersens", true)) {
            nvsReady = true;
            prefs.end();
            Serial.println(F("[NVS] Namespace 'watersens' created safely and verified."));
            return;
        }
    }

    nvsReady = false;
    Serial.println(F("[NVS] ERROR: Unable to initialize NVS namespace 'watersens'."));
}

// ----------------------------------------------------------------------------
// Setup Entrypoint
// ----------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println();
    Serial.println(F("=========================================================="));
    Serial.println(F(" HYDROSENSE SMART WATER QUALITY MONITOR — ESP32 FIRMWARE  "));
    Serial.printf (" Calibration Config Version: %s\n", CAL_CONFIG_VERSION);
    Serial.println(F("=========================================================="));

    analogReadResolution(ESP32_ADC_RESOLUTION_BITS); // 12-bit (0 - 4095)
    analogSetAttenuation(ADC_11db);                  // 11dB (~0 - 3.1V)
    Serial.println(F("[SETUP] ESP32 ADC configured: 12-bit resolution, 11dB attenuation."));

    ensureNvsNamespaceInitialized();

    if (displayManager.begin()) {
        Serial.println(F("[SETUP] OLED SSD1306 initialized successfully (0x3C)."));
    } else {
        Serial.println(F("[SETUP] WARNING: OLED SSD1306 initialization failed or not detected."));
    }

    alertManager.begin();
    Serial.println(F("[SETUP] Buzzer subsystem initialized on GPIO25. Startup chirp emitted."));

    sensorValidator.begin();
    phSensor.begin();
    turbSensor.begin();
    tdsSensor.begin();
    Serial.println(F("[SETUP] pH Sensor initialized on GPIO34 (ADC1_CH6, ÷2.5 divider)."));
    Serial.println(F("[SETUP] Turbidity Sensor initialized on GPIO32 (ADC1_CH4, ÷2.5 divider)."));
    Serial.printf("[SETUP] TDS Sensor on GPIO35 (Direct 3.3V, 1.0x): %s\n",
                  tdsSensor.isAvailable() ? "ENABLED" : "DISABLED");

    cloudManager.begin();

    Serial.println(F("----------------------------------------------------------"));
    Serial.println(F("Type 'cal help' for calibration & 'status' for diagnostics."));
    Serial.println(F("=========================================================="));
    Serial.println();
}

// ----------------------------------------------------------------------------
// Main Non-Blocking Executive Loop
// ----------------------------------------------------------------------------
void loop() {
    uint32_t currentMillis = millis();

    if (currentMillis - lastSensorSampleMillis >= SENSOR_SAMPLE_INTERVAL_MS) {
        lastSensorSampleMillis = currentMillis;

        phReading   = phSensor.read();
        turbReading = turbSensor.read();
        tdsReading  = tdsSensor.read();
        applyPhPresentationEstimate();

        bool isWifi = cloudManager.isWifiConnected();
        bool isCloudOk = cloudManager.isCloudHealthy();

        sensorValidator.evaluate(
            phReading,
            turbReading,
            tdsReading,
            isWifi,
            isCloudOk,
            tdsSensor.isCalibrated(),
            phSensor.isProvisional(),
            turbSensor.isProvisional()
        );
    }

    alertManager.update(currentMillis,
                        sensorValidator.getThresholdSeverity(),
                        sensorValidator.shouldSoundBuzzer());

    displayManager.update(currentMillis,
                          phReading,
                          turbReading,
                          tdsReading,
                          sensorValidator,
                          cloudManager.isWifiConnected(),
                          cloudManager.getOledTag());

    cloudManager.update(currentMillis,
                        phReading,
                        turbReading,
                        tdsReading,
                        sensorValidator);

    if (currentMillis - lastSerialLogMillis >= 2000) {
        lastSerialLogMillis = currentMillis;

        bool hasPh = (phReading.isValid && !isnan(phReading.calibratedValue) && phReading.status != STATUS_CALIBRATION_PENDING);
        bool hasTurb = (turbReading.isValid && !isnan(turbReading.calibratedValue) && turbReading.status != STATUS_CALIBRATION_PENDING);
        bool hasTds = (tdsReading.isValid && !isnan(tdsReading.calibratedValue) && tdsReading.status != STATUS_CALIBRATION_PENDING);

        String wqsStr = sensorValidator.isWqsValid() ? String(sensorValidator.getWqs(), 1) : String("N/A");

        Serial.printf("[TELEMETRY] Mode:%s | pH:%s | Turb:%s | TDS:%s | WQS:%s | WStatus:%d(%s) | Sev:%s | Buzzer:%s | Health:0x%04X | Net:%s\n",
                      sensorValidator.getModeShortTag(),
                      hasPh ? (String(phReading.calibratedValue, 2) + "pH").c_str() : phReading.message,
                      hasTurb ? (String(turbReading.calibratedValue, 1) + "NTU").c_str() : turbReading.message,
                      hasTds ? (String(tdsReading.calibratedValue, 0) + "ppm").c_str() : tdsReading.message,
                      wqsStr.c_str(),
                      sensorValidator.getWaterStatusCode(),
                      sensorValidator.getWaterStatusLabel(),
                      sensorValidator.getSeverityName(),
                      sensorValidator.shouldSoundBuzzer() ? "ON" : "OFF",
                      sensorValidator.getHealthCode(),
                      cloudManager.getStatusText());

        if (phReading.status == STATUS_OVER_RANGE || turbReading.status == STATUS_OVER_RANGE || tdsReading.status == STATUS_OVER_RANGE) {
            Serial.println(F("[SAFETY ALARM] ELECTRICAL OVER-RANGE DETECTED! ADC >= 3.05V! Check wiring immediately!"));
        }
    }

    processSerialCommands();
}

// The physical pH signal remains in SensorReading's voltage fields. Only a
// provisional, calibration-pending pH display is filled from the existing TDS
// and turbidity results. Hardware faults and verified NVS pH values are never
// replaced; SensorValidator still receives phSensor.isProvisional() so WQS and
// hazards keep their existing calibration safety behaviour.
void applyPhPresentationEstimate() {
    if (phSensor.isCalibrated() || !phSensor.isProvisional() ||
        !phReading.isValid || phReading.status != STATUS_CALIBRATION_PENDING ||
        !isnan(phReading.calibratedValue)) {
        return;
    }
    if (!tdsReading.isValid || !turbReading.isValid ||
        isnan(tdsReading.calibratedValue) || isnan(turbReading.calibratedValue)) {
        return;
    }

    const PhDemoDisplayConfig config = {
        PH_DEMO_RO_TDS_PPM,
        PH_DEMO_TAP_TDS_PPM,
        PH_DEMO_RO_TURBIDITY,
        PH_DEMO_TAP_TURBIDITY,
        PH_DEMO_RO_DEFAULT,
        PH_DEMO_TAP_DEFAULT,
        PH_DEMO_MIN,
        PH_DEMO_MAX,
        PH_DEMO_CONTAMINATED_RISE,
        PH_DEMO_CONTAMINATED_ADJUSTMENT,
        PH_DEMO_FILTER_ALPHA
    };
    const float estimate = phDisplayEstimator.update(
        tdsReading.calibratedValue, turbReading.calibratedValue, config);
    if (isnan(estimate)) return;

    phReading.calibratedValue = estimate;
    phReading.status = STATUS_OK;
    snprintf(phReading.message, sizeof(phReading.message), "pH DISPLAY ESTIMATE");
}

// ----------------------------------------------------------------------------
// Guided Calibration Handlers
// ----------------------------------------------------------------------------
void handlePhCalibrationPoint(float targetPh) {
    Serial.println();
    Serial.printf("[CAL-pH] Capturing pH %.2f buffer reading (30 oversampled readings)...\n", targetPh);

    float raw = 0.0f, adcMv = 0.0f, boardMv = 0.0f, stdAdcMv = 0.0f, stdBoardMv = 0.0f;
    phSensor.acquireCalibrationSample(raw, adcMv, boardMv, stdAdcMv, stdBoardMv);

    Serial.printf("[CAL-pH] Raw ADC       : %.1f\n", raw);
    Serial.printf("[CAL-pH] ADC mV        : %.1f mV (sigma = %.2f mV)\n", adcMv, stdAdcMv);
    Serial.printf("[CAL-pH] Board mV (x2.5): %.1f mV (sigma = %.2f mV)\n", boardMv, stdBoardMv);

    if (raw >= ADC_OVER_RANGE_RAW || (adcMv / 1000.0f) >= ADC_OVER_RANGE_VOLTS) {
        Serial.println(F("[CAL-pH] REJECTED: ADC electrical over-range (>= 3.05V)! Check divider wiring."));
        return;
    }
    if (raw < ADC_DISCONNECTED_RAW || (adcMv / 1000.0f) < ADC_DISCONNECTED_VOLTS) {
        Serial.println(F("[CAL-pH] REJECTED: Sensor disconnected / 0V. Connect probe and rinse/immerse."));
        return;
    }
    float chosenMv = PH_CAL_IS_BOARD_MV ? boardMv : adcMv;
    float chosenStd = PH_CAL_IS_BOARD_MV ? stdBoardMv : stdAdcMv;
    if (chosenStd > PH_CAL_MAX_STDDEV_MV) {
        Serial.printf("[CAL-pH] REJECTED: Voltage unstable (sigma=%.2f mV > %.1f mV). Let stabilize 30-60s and retry.\n",
                      chosenStd, PH_CAL_MAX_STDDEV_MV);
        return;
    }

    if (fabsf(targetPh - 4.01f) < 0.05f) {
        phStage.v4Mv = chosenMv;
        phStage.has4 = true;
    } else if (fabsf(targetPh - 7.00f) < 0.05f) {
        phStage.v7Mv = chosenMv;
        phStage.has7 = true;
    } else {
        phStage.v9Mv = chosenMv;
        phStage.has9 = true;
    }

    Serial.printf("[CAL-pH] CAPTURED pH %.2f -> %.1f mV (%s).\n",
                  targetPh, chosenMv, PH_CAL_IS_BOARD_MV ? "Reconstructed Board mV" : "ADC mV");
    evaluateAndReportPhProposal();
}

void evaluateAndReportPhProposal() {
    phStage.proposalValid = false;
    if (!phStage.has4 || !phStage.has7 || !phStage.has9) {
        Serial.print(F("[CAL-pH] Missing staged buffers:"));
        if (!phStage.has4) Serial.print(F(" [ph cal 4.01]"));
        if (!phStage.has7) Serial.print(F(" [ph cal 7.00]"));
        if (!phStage.has9) Serial.print(F(" [ph cal 9.18]"));
        Serial.println();
        return;
    }

    PhThreePointCal cal = buildPhThreePointCalibration(phStage.v4Mv, phStage.v7Mv, phStage.v9Mv, PH_CAL_IS_BOARD_MV);
    Serial.println(F("-------------------- pH 3-POINT PROPOSAL --------------------"));
    Serial.printf("pH 4.01 : %.1f mV | pH 7.00 : %.1f mV | pH 9.18 : %.1f mV\n",
                  phStage.v4Mv, phStage.v7Mv, phStage.v9Mv);
    if (!cal.isValid) {
        Serial.println(F("Validity: INVALID / REJECTED (check ordering, separation >= 50mV, or monotonic sign)."));
        Serial.println(F("-------------------------------------------------------------"));
        return;
    }
    phStage.proposalValid = true;
    Serial.printf("acidSlope : %.6f pH/mV (%.3f pH/V)\n", cal.acidSlope, cal.acidSlope * 1000.0f);
    Serial.printf("baseSlope : %.6f pH/mV (%.3f pH/V)\n", cal.baseSlope, cal.baseSlope * 1000.0f);
    Serial.println(F("Validity  : VALID"));
    Serial.println(F("Run 'cal save' or 'ph confirm' to commit to NVS."));
    Serial.println(F("-------------------------------------------------------------"));
}

void handleTurbClearCapture(float knownClearNtu) {
    if (isnan(knownClearNtu) || knownClearNtu < 0.0f || knownClearNtu > 100.0f) {
        Serial.println(F("[CAL-Turb] Usage: 'turb cal clear <known_NTU>' (e.g. 'turb cal clear 0.2')."));
        return;
    }
    Serial.printf("\n[CAL-Turb] Capturing CLEAR reference (%.2f NTU, 30 oversampled readings)...\n", knownClearNtu);
    float raw = 0.0f, adcMv = 0.0f, boardMv = 0.0f, stdAdcMv = 0.0f, stdBoardMv = 0.0f;
    turbSensor.acquireCalibrationSample(raw, adcMv, boardMv, stdAdcMv, stdBoardMv);

    Serial.printf("[CAL-Turb] Raw ADC       : %.1f\n", raw);
    Serial.printf("[CAL-Turb] ADC mV        : %.1f mV (sigma = %.2f mV)\n", adcMv, stdAdcMv);
    Serial.printf("[CAL-Turb] Board mV (x2.5): %.1f mV (sigma = %.2f mV)\n", boardMv, stdBoardMv);

    if (raw >= ADC_OVER_RANGE_RAW || (adcMv / 1000.0f) >= ADC_OVER_RANGE_VOLTS) {
        Serial.println(F("[CAL-Turb] REJECTED: ADC electrical over-range (>= 3.05V)!"));
        return;
    }
    if (raw < ADC_DISCONNECTED_RAW || (adcMv / 1000.0f) < ADC_DISCONNECTED_VOLTS) {
        Serial.println(F("[CAL-Turb] REJECTED: Sensor disconnected / 0V. Check 5V power and GPIO32 wiring."));
        return;
    }
    float chosenMv = TURB_CAL_IS_BOARD_MV ? boardMv : adcMv;
    float chosenStd = TURB_CAL_IS_BOARD_MV ? stdBoardMv : stdAdcMv;
    if (chosenStd > TURB_CAL_MAX_STDDEV_MV) {
        Serial.printf("[CAL-Turb] REJECTED: Unstable voltage (sigma=%.2f mV > %.1f mV).\n", chosenStd, TURB_CAL_MAX_STDDEV_MV);
        return;
    }

    turbStage.vClearMv = chosenMv;
    turbStage.ntuClear = knownClearNtu;
    turbStage.hasClear = true;
    Serial.printf("[CAL-Turb] CAPTURED Clear Reference: %.1f mV @ %.2f NTU.\n", chosenMv, knownClearNtu);
    evaluateAndReportTurbProposal();
}

void handleTurbStdCapture(float knownStdNtu) {
    if (isnan(knownStdNtu) || knownStdNtu <= 0.0f || knownStdNtu > 3000.0f) {
        Serial.println(F("[CAL-Turb] Usage: 'turb cal std <known_NTU>' (e.g. 'turb cal std 100')."));
        return;
    }
    Serial.printf("\n[CAL-Turb] Capturing STANDARD reference (%.2f NTU, 30 oversampled readings)...\n", knownStdNtu);
    float raw = 0.0f, adcMv = 0.0f, boardMv = 0.0f, stdAdcMv = 0.0f, stdBoardMv = 0.0f;
    turbSensor.acquireCalibrationSample(raw, adcMv, boardMv, stdAdcMv, stdBoardMv);

    Serial.printf("[CAL-Turb] Raw ADC       : %.1f\n", raw);
    Serial.printf("[CAL-Turb] ADC mV        : %.1f mV (sigma = %.2f mV)\n", adcMv, stdAdcMv);
    Serial.printf("[CAL-Turb] Board mV (x2.5): %.1f mV (sigma = %.2f mV)\n", boardMv, stdBoardMv);

    if (raw >= ADC_OVER_RANGE_RAW || (adcMv / 1000.0f) >= ADC_OVER_RANGE_VOLTS) {
        Serial.println(F("[CAL-Turb] REJECTED: ADC electrical over-range (>= 3.05V)!"));
        return;
    }
    if (raw < ADC_DISCONNECTED_RAW || (adcMv / 1000.0f) < ADC_DISCONNECTED_VOLTS) {
        Serial.println(F("[CAL-Turb] REJECTED: Sensor disconnected / 0V."));
        return;
    }
    float chosenMv = TURB_CAL_IS_BOARD_MV ? boardMv : adcMv;
    float chosenStd = TURB_CAL_IS_BOARD_MV ? stdBoardMv : stdAdcMv;
    if (chosenStd > TURB_CAL_MAX_STDDEV_MV) {
        Serial.printf("[CAL-Turb] REJECTED: Unstable voltage (sigma=%.2f mV > %.1f mV).\n", chosenStd, TURB_CAL_MAX_STDDEV_MV);
        return;
    }

    turbStage.vStdMv = chosenMv;
    turbStage.ntuStd = knownStdNtu;
    turbStage.hasStd = true;
    Serial.printf("[CAL-Turb] CAPTURED Standard Reference: %.1f mV @ %.2f NTU.\n", chosenMv, knownStdNtu);
    evaluateAndReportTurbProposal();
}

void evaluateAndReportTurbProposal() {
    turbStage.proposalValid = false;
    if (!turbStage.hasClear || !turbStage.hasStd) {
        Serial.print(F("[CAL-Turb] Missing staged points:"));
        if (!turbStage.hasClear) Serial.print(F(" [turb cal clear <ntu>]"));
        if (!turbStage.hasStd)   Serial.print(F(" [turb cal std <ntu>]"));
        Serial.println();
        return;
    }

    TurbidityCal cal = buildTurbidityCalibration(
        turbStage.vClearMv, turbStage.ntuClear,
        turbStage.vStdMv, turbStage.ntuStd,
        turbStage.vStdMv, turbStage.vClearMv,
        turbStage.ntuClear, turbStage.ntuStd,
        TURB_CAL_IS_BOARD_MV
    );

    Serial.println(F("----------------- TURBIDITY CURVE PROPOSAL -----------------"));
    Serial.printf("Clear Ref   : %.1f mV @ %.2f NTU\n", turbStage.vClearMv, turbStage.ntuClear);
    Serial.printf("Std Ref     : %.1f mV @ %.2f NTU\n", turbStage.vStdMv, turbStage.ntuStd);
    if (!cal.isValid) {
        Serial.println(F("Validity    : INVALID / REJECTED (requires V_clear > V_std by >=150mV and ntuStd > ntuClear)."));
        Serial.println(F("------------------------------------------------------------"));
        return;
    }
    turbStage.proposalValid = true;
    Serial.printf("Slope       : %.4f NTU/V (decreasing voltage with increasing turbidity)\n",
                  (cal.ntuStd - cal.ntuClear) / ((cal.vClearMv - cal.vStdMv) / 1000.0f));
    Serial.printf("Valid Span  : %.1f - %.1f mV | %.2f - %.2f NTU\n",
                  cal.vMinMv, cal.vMaxMv, cal.ntuMin, cal.ntuMax);
    Serial.println(F("Validity    : VALID"));
    Serial.println(F("Run 'cal save' or 'turb confirm' to commit to NVS."));
    Serial.println(F("------------------------------------------------------------"));
}

void handleTdsVerifyCapture(float knownRefPpm) {
    if (knownRefPpm < TDS_CAL_MIN_PPM || knownRefPpm > TDS_CAL_MAX_PPM) {
        Serial.println(F("[CAL-TDS] Usage: 'tds verify <known_ppm>' (10 - 3000 ppm, e.g. 'tds verify 342')."));
        return;
    }
    Serial.printf("\n[CAL-TDS] Capturing verification sample in %.1f ppm standard (25C nom.)...\n", knownRefPpm);
    float avgV = 0.0f, stdDevV = 0.0f, avgRaw = 0.0f;
    tdsSensor.acquireCalibrationReading(avgV, stdDevV, &avgRaw);
    float adcMv = avgV * 1000.0f;
    float stdMv = stdDevV * 1000.0f;

    Serial.printf("[CAL-TDS] Raw ADC        : %.1f\n", avgRaw);
    Serial.printf("[CAL-TDS] ADC mV (1.0x)  : %.1f mV (sigma = %.2f mV)\n", adcMv, stdMv);

    TdsConfigBounds b = TDSSensor::getBounds();
    TdsProposalEvaluation prop = evaluateTdsCalibrationProposal(
        tdsSensor.isAvailable(), avgV, stdDevV, avgRaw, knownRefPpm,
        tdsSensor.hasDryBaseline(), tdsSensor.getDryBaselineVoltage(), b
    );
    if (!prop.accepted) {
        Serial.printf("[CAL-TDS] REJECTED (validation code=%d). Check immersion/stability/wiring.\n", (int)prop.status);
        tdsStage.hasProposal = false;
        return;
    }

    float predictedPpm = prop.rawPolynomialPpm;
    float errPct = ((predictedPpm - knownRefPpm) / knownRefPpm) * 100.0f;
    tdsStage.hasProposal = true;
    tdsStage.vAdcVolts = avgV;
    tdsStage.rawAdc = avgRaw;
    tdsStage.refPpm = knownRefPpm;
    tdsStage.proposedK = prop.candidateKFactor;

    Serial.println(F("----------------- TDS VERIFICATION RESULT ------------------"));
    Serial.printf("Reference Standard   : %.1f ppm\n", knownRefPpm);
    Serial.printf("Predicted Polynomial : %.1f ppm (T_nom=%.1fC, k=1.00)\n", predictedPpm, TDS_NOMINAL_TEMP_C);
    Serial.printf("Deviation            : %+.2f %%\n", errPct);
    Serial.printf("Proposed kFactor     : %.4f\n", prop.candidateKFactor);
    Serial.println(F("Note: kFactor is NOT applied automatically."));
    Serial.println(F("Run 'tds confirm' (or 'cal save') ONLY to apply & store this kFactor in NVS."));
    Serial.println(F("------------------------------------------------------------"));
}

bool commitStagedPhCalibration() {
    if (!phStage.proposalValid) return false;
    bool ok = phSensor.setThreePointCalibration(phStage.v4Mv, phStage.v7Mv, phStage.v9Mv, PH_CAL_IS_BOARD_MV, true);
    if (ok) {
        Serial.println(F("[CAL-pH] SAVED & VERIFIED in NVS namespace 'watersens'."));
        phStage.has4 = phStage.has7 = phStage.has9 = phStage.proposalValid = false;
    } else {
        Serial.println(F("[CAL-pH] ERROR: Failed to save pH calibration to NVS."));
    }
    return ok;
}

bool commitStagedTurbCalibration() {
    if (!turbStage.proposalValid) return false;
    bool ok = turbSensor.setFinalCalibration(
        turbStage.vClearMv, turbStage.ntuClear,
        turbStage.vStdMv, turbStage.ntuStd,
        turbStage.vStdMv, turbStage.vClearMv,
        turbStage.ntuClear, turbStage.ntuStd,
        TURB_CAL_IS_BOARD_MV, true
    );
    if (ok) {
        Serial.println(F("[CAL-Turb] SAVED & VERIFIED in NVS namespace 'watersens'."));
        turbStage.hasClear = turbStage.hasStd = turbStage.proposalValid = false;
    } else {
        Serial.println(F("[CAL-Turb] ERROR: Failed to save Turbidity calibration to NVS."));
    }
    return ok;
}

bool commitStagedTdsCalibration() {
    if (!tdsStage.hasProposal) return false;
    bool ok = tdsSensor.setCalibrationFromReference(tdsStage.refPpm, tdsStage.vAdcVolts, true, tdsStage.rawAdc);
    if (ok) {
        Serial.printf("[CAL-TDS] SAVED & VERIFIED kFactor=%.4f in NVS namespace 'watersens'.\n", tdsSensor.getKFactor());
        tdsStage.hasProposal = false;
    } else {
        Serial.println(F("[CAL-TDS] ERROR: Failed to save TDS kFactor to NVS."));
    }
    return ok;
}

// ----------------------------------------------------------------------------
// Serial Diagnostic & Guided Calibration Command Processor
// ----------------------------------------------------------------------------
void processSerialCommands() {
    if (!Serial.available()) return;

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) return;

    String lower = cmd;
    lower.toLowerCase();

    if (lower == "help" || lower == "?" || lower == "cal help") {
        printHelpMenu();
    } else if (lower == "status") {
        printDiagnostics();
    } else if (lower == "cal status" || lower == "cal") {
        printCalibrationStatus();
    } else if (lower == "demo status" || lower == "demo") {
        printDemoStatus();
    } else if (lower == "net" || lower == "wifi") {
        cloudManager.printNetworkDiagnostics();
    } else if (lower == "buzzer test" || lower == "buzz test") {
        alertManager.triggerTestBeep();
        Serial.println(F("[BUZZER] Manual test chirp triggered on GPIO25."));
    } else if (lower == "mode drinking" || lower == "mode drink") {
        sensorValidator.setMode(MODE_DRINKING, true);
        printModeStatus();
    } else if (lower == "mode regular" || lower == "mode regular_usage" || lower == "mode usage") {
        sensorValidator.setMode(MODE_REGULAR_USAGE, true);
        printModeStatus();
    } else if (lower == "mode" || lower == "mode status") {
        printModeStatus();
    }
    // --- NVS Save / Reset Commands ---
    else if (lower == "cal save") {
        bool anyCommitted = false;
        if (phStage.proposalValid)   anyCommitted |= commitStagedPhCalibration();
        if (turbStage.proposalValid) anyCommitted |= commitStagedTurbCalibration();
        if (tdsStage.hasProposal)    anyCommitted |= commitStagedTdsCalibration();
        if (!anyCommitted) {
            bool savedExisting = false;
            if (phSensor.isCalibrated() && phSensor.isThreePoint()) savedExisting |= phSensor.saveCalibration();
            if (turbSensor.isCalibrated()) savedExisting |= turbSensor.saveCalibration();
            if (tdsSensor.isCalibrated())  savedExisting |= tdsSensor.saveCalibration();
            Serial.println(savedExisting
                ? F("[CAL] Verified existing active calibrations are saved in NVS.")
                : F("[CAL] Nothing complete to save. Capture required buffer/standard points first ('cal status')."));
        }
    } else if (lower == "cal reset") {
        phSensor.resetCalibration();
        turbSensor.resetCalibration();
        tdsSensor.resetCalibration();
        phStage = PhStagingState();
        turbStage = TurbStagingState();
        tdsStage = TdsVerifyStagingState();
        Serial.println(F("[CAL] Explicit reset complete: pH, Turbidity, and TDS NVS calibrations cleared."));
    }
    // --- Guided pH 3-Point Calibration Commands ---
    else if (lower == "ph cal" || lower == "ph help") {
        evaluateAndReportPhProposal();
    } else if (lower == "ph cal 4" || lower == "ph cal 4.01") {
        handlePhCalibrationPoint(4.01f);
    } else if (lower == "ph cal 7" || lower == "ph cal 7.00") {
        handlePhCalibrationPoint(7.00f);
    } else if (lower == "ph cal 9" || lower == "ph cal 9.18") {
        handlePhCalibrationPoint(9.18f);
    } else if (lower == "ph confirm" || lower == "ph save") {
        if (!commitStagedPhCalibration()) {
            Serial.println(F("[CAL-pH] Cannot save: complete 4.01, 7.00, and 9.18 captures first."));
        }
    } else if (lower == "ph cancel") {
        phStage = PhStagingState();
        Serial.println(F("[CAL-pH] Staged pH calibration points cleared."));
    } else if (lower == "ph reset") {
        phSensor.resetCalibration();
        phStage = PhStagingState();
        Serial.println(F("[CAL-pH] pH NVS calibration reset."));
    }
    // --- Guided Turbidity Calibration Commands ---
    else if (lower == "turb cal" || lower == "turb help") {
        evaluateAndReportTurbProposal();
    } else if (lower.startsWith("turb cal clear ")) {
        String arg = cmd.substring(15);
        arg.trim();
        handleTurbClearCapture(arg.length() > 0 ? arg.toFloat() : NAN);
    } else if (lower == "turb cal clear") {
        Serial.println(F("[CAL-Turb] Enter actual reference NTU for clear water, e.g. 'turb cal clear 0.2'"));
    } else if (lower.startsWith("turb cal std ")) {
        String arg = cmd.substring(13);
        arg.trim();
        handleTurbStdCapture(arg.length() > 0 ? arg.toFloat() : NAN);
    } else if (lower.startsWith("turb cal ")) {
        String arg = cmd.substring(9);
        arg.trim();
        handleTurbStdCapture(arg.length() > 0 ? arg.toFloat() : NAN);
    } else if (lower == "turb confirm" || lower == "turb save") {
        if (!commitStagedTurbCalibration()) {
            Serial.println(F("[CAL-Turb] Cannot save: capture valid clear & standard points first."));
        }
    } else if (lower == "turb cancel") {
        turbStage = TurbStagingState();
        Serial.println(F("[CAL-Turb] Staged turbidity calibration points cleared."));
    } else if (lower == "turb reset") {
        turbSensor.resetCalibration();
        turbStage = TurbStagingState();
        Serial.println(F("[CAL-Turb] Turbidity NVS calibration reset."));
    }
    // --- Guided TDS Verification & Dry Baseline Commands ---
    else if (lower == "tds dry") {
        float avgV = 0.0f, stdDevV = 0.0f, avgRaw = 0.0f;
        tdsSensor.acquireCalibrationReading(avgV, stdDevV, &avgRaw);
        Serial.printf("[CAL-TDS] Dry Probe Capture: Raw=%.1f | ADC=%.1f mV (sigma=%.2f mV)\n",
                      avgRaw, avgV * 1000.0f, stdDevV * 1000.0f);
        if ((stdDevV * 1000.0f) > 50.0f) {
            Serial.println(F("[CAL-TDS] REJECTED: Unstable dry voltage."));
        } else if (tdsSensor.setDryBaseline(avgV, true)) {
            Serial.printf("[CAL-TDS] Dry baseline saved to NVS (V_dry=%.3fV).\n", avgV);
        } else {
            Serial.println(F("[CAL-TDS] REJECTED: Dry baseline out of bounds (>= 1.0V)."));
        }
    } else if (lower == "tds dry clear") {
        tdsSensor.clearDryBaseline();
        Serial.println(F("[CAL-TDS] Dry baseline cleared from NVS."));
    } else if (lower.startsWith("tds verify ") || lower.startsWith("tds cal ")) {
        int sp = cmd.lastIndexOf(' ');
        float ppm = (sp > 0) ? cmd.substring(sp + 1).toFloat() : 0.0f;
        handleTdsVerifyCapture(ppm);
    } else if (lower == "tds verify" || lower == "tds cal") {
        Serial.println(F("[CAL-TDS] Usage: 'tds verify <ppm>' (e.g. 'tds verify 342')."));
    } else if (lower == "tds confirm" || lower == "tds save") {
        if (!commitStagedTdsCalibration()) {
            Serial.println(F("[CAL-TDS] No TDS verification staged. Run 'tds verify <ppm>' first."));
        }
    } else if (lower == "tds cancel") {
        tdsStage = TdsVerifyStagingState();
        Serial.println(F("[CAL-TDS] Staged TDS verification cleared."));
    } else if (lower == "tds reset") {
        tdsSensor.resetCalibration();
        tdsStage = TdsVerifyStagingState();
    } else {
        Serial.printf("[CLI] Unknown command: '%s'. Type 'cal help' for commands.\n", cmd.c_str());
    }
}

void printHelpMenu() {
    Serial.println();
    Serial.println(F("================================================================================"));
    Serial.println(F("              HYDROSENSE — CALIBRATION & SYSTEM DIAGNOSTICS MENU                "));
    Serial.println(F("================================================================================"));
    Serial.println(F(" General & Verification:"));
    Serial.println(F("   status              : Raw ADC, mV, board V, values, WQS, WStatus, Health, NVS, Cloud"));
    Serial.println(F("   cal status          : NVS status, stored coefficients & missing points"));
    Serial.println(F("   cal save            : Commit validated staged calibrations to NVS"));
    Serial.println(F("   cal reset           : Clear all sensor calibrations from NVS"));
    Serial.println(F("   cal help / help     : Show this menu"));
    Serial.println(F("   demo status         : Show demo simulation state"));
    Serial.println(F("   net / wifi          : Print Wi-Fi & ThingSpeak Channel 3570138 diagnostics"));
    Serial.println(F("   mode status/drinking/regular : Inspect or switch water quality limits"));
    Serial.println(F("   buzzer test         : Trigger manual diagnostic chirp on GPIO25"));
    Serial.println();
    Serial.println(F(" pH 3-Point Guided Calibration (GPIO34, 15k/10k 2.5x):"));
    Serial.println(F("   ph cal 4.01         : Capture stable voltage in pH 4.01 buffer"));
    Serial.println(F("   ph cal 7.00         : Capture stable voltage in pH 7.00 buffer"));
    Serial.println(F("   ph cal 9.18         : Capture stable voltage in pH 9.18 buffer"));
    Serial.println(F("   ph confirm          : Validate & save 3-point pH slopes to NVS ('ph cancel'/'ph reset')"));
    Serial.println();
    Serial.println(F(" Turbidity Guided Calibration (GPIO32, 15k/10k 2.5x):"));
    Serial.println(F("   turb cal clear <ntu>: Capture clear reference with known NTU (e.g. 0.2)"));
    Serial.println(F("   turb cal std <ntu>  : Capture certified standard (e.g. 'turb cal std 100')"));
    Serial.println(F("   turb confirm        : Validate curve & save to NVS ('turb cancel'/'turb reset')"));
    Serial.println();
    Serial.println(F(" TDS Verification & Optional kFactor (GPIO35, Direct 1.0x):"));
    Serial.println(F("   tds dry             : Capture dry-in-air baseline ('tds dry clear' to remove)"));
    Serial.println(F("   tds verify <ppm>    : Compare 25C polynomial vs reference (e.g. 'tds verify 342')"));
    Serial.println(F("   tds confirm         : Explicitly save derived kFactor to NVS ('tds cancel'/'tds reset')"));
    Serial.println(F("================================================================================"));
    Serial.println();
}

void printDemoStatus() {
    Serial.println();
    Serial.println(F("==================== DEMO MODE STATUS ===================="));
    Serial.printf("FEATURE_DEMO_MODE         : %s\n", FEATURE_DEMO_MODE ? "ENABLED (99=Demo)" : "DISABLED (Normal Operation)");
    Serial.printf("Calibration Config Ver    : %s\n", CAL_CONFIG_VERSION);
    Serial.printf("Current Water Status Code : %d (%s)\n",
                  sensorValidator.getWaterStatusCode(), sensorValidator.getWaterStatusLabel());
    Serial.println(F("=========================================================="));
    Serial.println();
}

void printModeStatus() {
    const ModeThresholds& th = sensorValidator.getActiveThresholds();
    Serial.println();
    Serial.println(F("==================== WATER QUALITY MODE STATUS ===================="));
    Serial.printf("Active Mode         : %s\n", sensorValidator.getModeName());
    Serial.printf("pH Allowed Range    : %.2f - %.2f (Hazard <%.1f or >%.1f)\n",
                  th.phMin, th.phMax, HAZARD_PH_MIN, HAZARD_PH_MAX);
    Serial.printf("Turbidity Limit     : <= %.2f NTU (Hazard >%.0f NTU)\n", th.turbMax, HAZARD_TURB_MAX_NTU);
    Serial.printf("TDS Limit           : <= %.0f ppm (Hazard >%.0f ppm)\n", th.tdsMax, HAZARD_TDS_MAX_PPM);
    Serial.printf("Buzzer Armed State  : %s\n", sensorValidator.shouldSoundBuzzer() ? "ALARMING" : "SILENT");
    Serial.println(F("==================================================================="));
    Serial.println();
}

void printCalibrationStatus() {
    Serial.println();
    Serial.println(F("==================== SENSOR CALIBRATION STATUS ===================="));
    Serial.printf("Calibration Config Version : %s\n", CAL_CONFIG_VERSION);
    Serial.printf("NVS Namespace 'watersens'  : %s\n", nvsReady ? "READY (Preserved)" : "UNAVAILABLE");
    Serial.println();

    Serial.println(F("--- [1] pH Sensor (GPIO34, 15k/10k Divider, 2.5x) ---"));
    Serial.printf("Status              : %s\n",
                  phSensor.isCalibrated()
                      ? (phSensor.isThreePoint() ? "CALIBRATED (NVS 3-Point 4.01/7.00/9.18)" : "CALIBRATED (Legacy NVS 2-Point)")
                      : (phSensor.isProvisional() ? "PROVISIONAL ESTIMATE (Not Experimentally Calibrated)" : "CALIBRATION PENDING"));
    Serial.printf("NVS Diagnostics     : %s\n", phSensor.getNvsDiagnostic());
    Serial.printf("Live Voltages       : V_adc=%.1f mV | V_board=%.1f mV\n",
                  phReading.adcVoltage * 1000.0f, phReading.reconstructedVoltage * 1000.0f);
    if (phSensor.hasCalibrationModel()) {
        if (phSensor.isThreePoint()) {
            const PhThreePointCal& c = phSensor.getThreePointCal();
            Serial.printf("Buffer Voltages (mV): V4=%.1f | V7=%.1f | V9=%.1f (%s)\n",
                          c.v4Mv, c.v7Mv, c.v9Mv, c.isBoardMv ? "Board mV" : "ADC mV");
            Serial.printf("Acid/Base Slopes    : acid=%.6f pH/mV | base=%.6f pH/mV\n",
                          c.acidSlope, c.baseSlope);
        } else {
            Serial.printf("Legacy 2-Point (V)  : V7=%.3f V | V4=%.3f V | Slope=%.3f pH/V\n",
                          phSensor.getVPh7(), phSensor.getVPh4(), phSensor.getSlope());
        }
    } else {
        Serial.println(F("Required            : Capture 'ph cal 4.01', 'ph cal 7.00', 'ph cal 9.18' -> 'ph confirm'."));
    }

    Serial.println();
    Serial.println(F("--- [2] Turbidity Sensor (GPIO32, 15k/10k Divider, 2.5x) ---"));
    Serial.printf("Status              : %s\n",
                  turbSensor.isCalibrated()
                      ? "CALIBRATED (NVS Verified)"
                      : (turbSensor.isProvisional() ? "PROVISIONAL ESTIMATE (Not Experimentally Calibrated)" : "CALIBRATION PENDING"));
    Serial.printf("NVS Diagnostics     : %s\n", turbSensor.getNvsDiagnostic());
    Serial.printf("Live Voltages       : V_adc=%.1f mV | V_board=%.1f mV\n",
                  turbReading.adcVoltage * 1000.0f, turbReading.reconstructedVoltage * 1000.0f);
    if (turbSensor.hasCalibrationModel()) {
        const TurbidityCal& tc = turbSensor.getCalibrationModel();
        Serial.printf("Active Curve        : Clear=%.1fmV (%.2f NTU) | Std=%.1fmV (%.2f NTU)\n",
                      tc.vClearMv, tc.ntuClear, tc.vStdMv, tc.ntuStd);
        Serial.printf("Supported Range     : %.1f - %.1f mV | %.2f - %.2f NTU\n",
                      tc.vMinMv, tc.vMaxMv, tc.ntuMin, tc.ntuMax);
    } else {
        Serial.println(F("Required            : Capture 'turb cal clear <ntu>' & 'turb cal std <ntu>' -> 'turb confirm'."));
    }

    Serial.println();
    Serial.println(F("--- [3] TDS Sensor (GPIO35, Direct 3.3V ADC, 1.0x) ---"));
    Serial.printf("Calculation Status  : %s\n",
                  tdsSensor.isCalibrated()
                      ? "CALIBRATED (Reference-Verified kFactor)"
                      : "PROVISIONAL (25C Polynomial Model, unverified vs standard)");
    Serial.printf("NVS Diagnostics     : %s\n", tdsSensor.getNvsDiagnostic());
    Serial.printf("Live ADC Voltage    : %.1f mV (Direct 1.0x, Raw=%.1f)\n",
                  tdsReading.adcVoltage * 1000.0f, tdsReading.rawAdc);
    Serial.printf("Correction Factor   : k=%.4f (T_nom=%.1fC)\n", tdsSensor.getKFactor(), TDS_NOMINAL_TEMP_C);
    Serial.println(F("Optional Verify     : 'tds verify 342' -> 'tds confirm' (if adjusting kFactor)."));
    Serial.println(F("==================================================================="));
    Serial.println();
}

void printHealthBreakdown(uint16_t hc) {
    Serial.printf("Health Flags (0x%04X)     :", hc);
    if (hc == HEALTH_OK) {
        Serial.println(F(" ALL OK"));
        return;
    }
    if (hc & HEALTH_WIFI_DISCONNECTED) Serial.print(F(" WIFI_OFF"));
    if (hc & HEALTH_CLOUD_ERROR)       Serial.print(F(" CLOUD_ERR"));
    if (hc & HEALTH_PH_FAULT)          Serial.print(F(" PH_FAULT"));
    if (hc & HEALTH_TURB_FAULT)        Serial.print(F(" TURB_FAULT"));
    if (hc & HEALTH_ADC_OVER_RANGE)    Serial.print(F(" ADC_OVER_RANGE"));
    if (hc & HEALTH_TDS_UNAVAILABLE)   Serial.print(F(" TDS_UNAVAIL"));
    if (hc & HEALTH_CALIBRATION_PENDING) Serial.print(F(" CAL_PENDING"));
    if (hc & HEALTH_DEMO_MODE_ACTIVE)  Serial.print(F(" DEMO"));
    if (hc & HEALTH_TDS_FAULT)         Serial.print(F(" TDS_FAULT"));
    if (hc & HEALTH_MODE_REGULAR)      Serial.print(F(" MODE_REG"));
    if (hc & HEALTH_TDS_DRY)           Serial.print(F(" TDS_DRY"));
    if (hc & HEALTH_TDS_PROVISIONAL)   Serial.print(F(" TDS_PROVISIONAL"));
    if (hc & HEALTH_PH_PROVISIONAL)    Serial.print(F(" PH_PROVISIONAL"));
    if (hc & HEALTH_TURB_PROVISIONAL)  Serial.print(F(" TURB_PROVISIONAL"));
    Serial.println();
}

void printDiagnostics() {
    Serial.println();
    Serial.println(F("==================== SYSTEM DIAGNOSTICS ===================="));
    Serial.printf("Calibration Config Ver    : %s\n", CAL_CONFIG_VERSION);
    Serial.printf("NVS Status                : %s\n", nvsReady ? "watersens READY" : "watersens FAILED");
    Serial.printf("Water Quality Mode        : %s\n", sensorValidator.getModeName());
    Serial.printf("pH (GPIO34, ÷2.5)         : Raw=%.1f | Adc=%.1fmV | Board=%.3fV | Val=%s | Cal=%s | %s\n",
                  phReading.rawAdc, phReading.adcVoltage * 1000.0f, phReading.reconstructedVoltage,
                  isnan(phReading.calibratedValue) ? "N/A" : String(phReading.calibratedValue, 2).c_str(),
                  phSensor.isCalibrated() ? "VERIFIED" : (phSensor.isProvisional() ? "PROVISIONAL" : "PENDING"),
                  phReading.message);
    Serial.printf("Turbidity (GPIO32, ÷2.5)  : Raw=%.1f | Adc=%.1fmV | Board=%.3fV | Val=%s | Cal=%s | %s\n",
                  turbReading.rawAdc, turbReading.adcVoltage * 1000.0f, turbReading.reconstructedVoltage,
                  isnan(turbReading.calibratedValue) ? "N/A" : String(turbReading.calibratedValue, 1).c_str(),
                  turbSensor.isCalibrated() ? "VERIFIED" : (turbSensor.isProvisional() ? "PROVISIONAL" : "PENDING"),
                  turbReading.message);
    Serial.printf("TDS (GPIO35, 1.0x Direct) : Raw=%.1f | Adc=%.1fmV | Val=%s | Calc=%s | %s\n",
                  tdsReading.rawAdc, tdsReading.adcVoltage * 1000.0f,
                  isnan(tdsReading.calibratedValue) ? "N/A" : String(tdsReading.calibratedValue, 0).c_str(),
                  tdsSensor.isCalibrated() ? "VERIFIED" : "PROVISIONAL(25C)",
                  tdsReading.message);
    Serial.printf("Water Quality Score (WQS) : %s (q_TDS=%s, q_pH=%s, q_Turb=%s)\n",
                  sensorValidator.isWqsValid() ? String(sensorValidator.getWqs(), 1).c_str() : "UNAVAILABLE",
                  isnan(sensorValidator.getSubIndexTds()) ? "--" : String(sensorValidator.getSubIndexTds(), 1).c_str(),
                  isnan(sensorValidator.getSubIndexPh()) ? "--" : String(sensorValidator.getSubIndexPh(), 1).c_str(),
                  isnan(sensorValidator.getSubIndexTurb()) ? "--" : String(sensorValidator.getSubIndexTurb(), 1).c_str());
    Serial.printf("WStatus                   : %d (%s)%s\n",
                  sensorValidator.getWaterStatusCode(),
                  sensorValidator.getWaterStatusLabel(),
                  sensorValidator.isCriticalHazard() ? " [CRITICAL HAZARD OVERRIDE]" : "");
    Serial.printf("Alert Severity / Buzzer   : %s (%d) | Buzzer=%s | %s\n",
                  sensorValidator.getSeverityName(), (int)sensorValidator.getSeverity(),
                  sensorValidator.shouldSoundBuzzer() ? "ACTIVE" : "SILENT",
                  sensorValidator.getAlertMessage());
    printHealthBreakdown(sensorValidator.getHealthCode());
    Serial.printf("ThingSpeak Connection     : Channel=%lu (%s) | WiFi=%s | Status=%s\n",
                  (unsigned long)THINGSPEAK_CHANNEL_ID,
                  THINGSPEAK_USE_5FIELD_PROFILE ? "5-field" : "8-field",
                  cloudManager.isWifiConnected() ? "YES" : "NO",
                  cloudManager.getStatusText());
    Serial.println(F("============================================================"));
    Serial.println();
}
