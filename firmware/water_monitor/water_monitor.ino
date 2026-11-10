/**
 * ============================================================================
 * SMART APARTMENT WATER QUALITY MONITOR - PHASE 1 ESP32 FIRMWARE
 * ============================================================================
 * Core Architecture: Non-blocking, modular, safety-critical embedded firmware.
 * 
 * Hardware:
 * - MCU: ESP32-D0WD-V3 (ESP32 Dev Module)
 * - pH Sensor: E201-C probe + Green signal board on GPIO34 (via 15k/10k divider)
 * - Turbidity: Optical probe + Red signal board on GPIO32 (via 15k/10k divider)
 * - TDS Sensor: Reserved on GPIO35 (Disabled in Phase 1, reports N/A)
 * - Display: SSD1306 128x64 OLED on I2C (SDA=21, SCL=22, addr=0x3C)
 * - Buzzer: Audio alert module on GPIO25
 * - Telemetry: ThingSpeak HTTP client ready for Phase 2 Python ingestion
 * ============================================================================
 */

#include "config.h"
#include "secrets.h"
#include "sensors/PHSensor.h"
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

uint32_t lastSensorSampleMillis = 0;
uint32_t lastSerialLogMillis    = 0;

// Forward Declarations
void processSerialCommands();
void printHelpMenu();
void printDiagnostics();
void printCalibrationStatus();
void printModeStatus();

// Calibration Bench Staging Variables
float pendingPhV7 = 0.0f;
float pendingPhV4 = 0.0f;
bool hasPendingPhV7 = false;
bool hasPendingPhV4 = false;

float pendingTurbVClear = 0.0f;
float pendingTurbVStd = 0.0f;
float pendingTurbNtuStd = 0.0f;
bool hasPendingTurbClear = false;
bool hasPendingTurbStd = false;

float pendingTdsVStd = 0.0f;
float pendingTdsPpmStd = 0.0f;
bool hasPendingTdsStd = false;

// ----------------------------------------------------------------------------
// Setup Entrypoint
// ----------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    delay(500); // Allow USB-UART bridge to stabilize

    Serial.println();
    Serial.println(F("=========================================================="));
    Serial.println(F(" SMART APARTMENT WATER QUALITY MONITOR — ESP32 FIRMWARE   "));
    Serial.println(F(" Phase 1: High-Reliability Sensor Acquisition & Telemetry  "));
    Serial.println(F("=========================================================="));

    // 1. Configure ESP32 Analog-to-Digital Converter
    // ADC1 is used exclusively (GPIO 32, 34, 35) to prevent Wi-Fi channel conflict.
    analogReadResolution(ESP32_ADC_RESOLUTION_BITS); // 12-bit (0 - 4095)
    analogSetAttenuation(ADC_11db);                  // 11dB attenuation (~0 - 3.1V range)
    Serial.println(F("[SETUP] ESP32 ADC configured: 12-bit resolution, 11dB attenuation."));

    // 2. Initialize OLED Display
    if (displayManager.begin()) {
        Serial.println(F("[SETUP] OLED SSD1306 initialized successfully (0x3C)."));
    } else {
        Serial.println(F("[SETUP] WARNING: OLED SSD1306 initialization failed or not detected."));
    }

    // 3. Initialize Audio Alerts (Plays startup chirp on GPIO25)
    alertManager.begin();
    Serial.println(F("[SETUP] Buzzer subsystem initialized on GPIO25. Startup chirp emitted."));

    // 4. Initialize Sensors & Validator Mode Settings
    sensorValidator.begin();
    phSensor.begin();
    turbSensor.begin();
    tdsSensor.begin();
    Serial.println(F("[SETUP] pH Sensor initialized on GPIO34 (ADC1_CH6, ÷2.5 divider)."));
    Serial.println(F("[SETUP] Turbidity Sensor initialized on GPIO32 (ADC1_CH4, ÷2.5 divider)."));
    Serial.printf("[SETUP] TDS Sensor on GPIO35 (Direct 3.3V, 1.0x): %s\n", 
                  tdsSensor.isAvailable() ? "ENABLED" : "DISABLED");

    // 5. Initialize Wi-Fi & Cloud Manager
    cloudManager.begin();

    // 6. Print Initial Electrical Safety Verification
    Serial.println(F("----------------------------------------------------------"));
    Serial.println(F("ELECTRICAL SAFETY REMINDER:"));
    Serial.println(F("Verify with a multimeter that GPIO voltages never exceed 3.0V"));
    Serial.println(F("(GPIO32 & GPIO34 via 15k/10k dividers; GPIO35 direct 3.3V TDS)."));
    Serial.println(F("Type 'help' in Serial Monitor for calibration & mode commands."));
    Serial.println(F("=========================================================="));
    Serial.println();
}

// ----------------------------------------------------------------------------
// Main Non-Blocking Executive Loop
// ----------------------------------------------------------------------------
void loop() {
    uint32_t currentMillis = millis();

    // 1. Read Physical Sensors at Configured Interval (e.g. 1.0s)
    if (currentMillis - lastSensorSampleMillis >= SENSOR_SAMPLE_INTERVAL_MS) {
        lastSensorSampleMillis = currentMillis;

        phReading   = phSensor.read();
        turbReading = turbSensor.read();
        tdsReading  = tdsSensor.read();

        // Evaluate system invariants, safety, mode thresholds, and alert severity
        bool isWifi = cloudManager.isWifiConnected();
        bool isCloudOk = cloudManager.isCloudHealthy();

        sensorValidator.evaluate(phReading, turbReading, tdsReading, isWifi, isCloudOk);
    }

    // 2. Update Alert Manager State Machine
    // STRICT RULE: Buzzer only activates on calibrated threshold violations!
    alertManager.update(currentMillis,
                        sensorValidator.getThresholdSeverity(),
                        sensorValidator.shouldSoundBuzzer());

    // 3. Update OLED Display Manager (Non-blocking screen refresh & rotation)
    displayManager.update(currentMillis, 
                          phReading, 
                          turbReading, 
                          tdsReading, 
                          sensorValidator, 
                          cloudManager.isWifiConnected(), 
                          cloudManager.getOledTag());

    // 4. Update Cloud Telemetry Manager (ThingSpeak HTTP POST every 20s)
    cloudManager.update(currentMillis, 
                        phReading, 
                        turbReading, 
                        tdsReading, 
                        sensorValidator);

    // 5. Periodic Diagnostics to Serial (Every 2 seconds)
    if (currentMillis - lastSerialLogMillis >= 2000) {
        lastSerialLogMillis = currentMillis;

        bool hasPh = (phReading.isValid && phReading.status != STATUS_CALIBRATION_PENDING && !isnan(phReading.calibratedValue));
        bool hasTurb = (turbReading.isValid && turbReading.status != STATUS_CALIBRATION_PENDING && !isnan(turbReading.calibratedValue));
        bool hasTds = (tdsReading.isValid && tdsReading.status != STATUS_CALIBRATION_PENDING && !isnan(tdsReading.calibratedValue));

        Serial.printf("[TELEMETRY] Mode:%s | pH:%s | Turb:%s | TDS:%s | Sev:%s | Buzzer:%s | Health:0x%04X | Net:%s\n",
                      sensorValidator.getModeShortTag(),
                      hasPh ? (String(phReading.calibratedValue, 2) + "pH").c_str() : phReading.message,
                      hasTurb ? (String(turbReading.calibratedValue, 1) + "NTU").c_str() : turbReading.message,
                      hasTds ? (String(tdsReading.calibratedValue, 0) + "ppm").c_str() : tdsReading.message,
                      sensorValidator.getSeverityName(),
                      sensorValidator.shouldSoundBuzzer() ? "ON" : "OFF",
                      sensorValidator.getHealthCode(),
                      cloudManager.getStatusText());

        // Highlight any electrical safety alarm
        if (phReading.status == STATUS_OVER_RANGE || turbReading.status == STATUS_OVER_RANGE || tdsReading.status == STATUS_OVER_RANGE) {
            Serial.println(F("[SAFETY ALARM] ELECTRICAL OVER-RANGE DETECTED! ADC >= 3.05V! Check wiring immediately!"));
        }
    }

    // 6. Interactive Serial CLI for Live Bench Calibration
    processSerialCommands();
}

// ----------------------------------------------------------------------------
// Interactive Serial Command Processing
// ----------------------------------------------------------------------------
void processSerialCommands() {
    if (!Serial.available()) return;

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) return;

    // --- General Commands ---
    if (cmd.equalsIgnoreCase("help") || cmd.equalsIgnoreCase("?") || cmd.equalsIgnoreCase("cal help")) {
        printHelpMenu();
    } else if (cmd.equalsIgnoreCase("status")) {
        printDiagnostics();
    } else if (cmd.equalsIgnoreCase("net") || cmd.equalsIgnoreCase("wifi")) {
        cloudManager.printNetworkDiagnostics();
    } else if (cmd.equalsIgnoreCase("cal status") || cmd.equalsIgnoreCase("cal")) {
        printCalibrationStatus();
    } 
    // --- pH Two-Point Calibration Workflow ---
    else if (cmd.equalsIgnoreCase("ph cal 7") || cmd.equalsIgnoreCase("ph cal 7.00") || 
             cmd.equalsIgnoreCase("ph point 7.00") || cmd.equalsIgnoreCase("ph 7") || cmd.equalsIgnoreCase("cal_ph7")) {
        Serial.println();
        Serial.println(F("[CAL-pH] === STEP 1: pH 7.00 BUFFER CALIBRATION ==="));
        Serial.println(F("[CAL-pH] Submerge probe into pH 7.00 buffer solution."));
        Serial.println(F("[CAL-pH] Stir gently for 5 seconds to eliminate bubbles, then hold steady."));
        Serial.println(F("[CAL-pH] Sampling 30 readings for signal stabilization..."));

        float avgV = 0.0f, stdDev = 0.0f;
        if (phSensor.acquireCalibrationReading(avgV, stdDev)) {
            if (stdDev > 0.050f) {
                Serial.printf("[CAL-pH] WARNING: Voltage unstable (V_avg=%.3fV, σ=%.4fV > 0.050V).\n", avgV, stdDev);
                Serial.println(F("[CAL-pH] Allow probe 30-60 seconds to thermally equilibrate, then retry 'ph cal 7.00'."));
            } else if (avgV < 0.10f || avgV > 4.95f) {
                Serial.printf("[CAL-pH] ERROR: Voltage %.3fV is out of physical circuit limits (0.10V - 4.95V).\n", avgV);
            } else {
                pendingPhV7 = avgV;
                hasPendingPhV7 = true;
                Serial.printf("[CAL-pH] SUCCESS: pH 7.00 point recorded -> V_pH7 = %.3f V (σ = %.4f V).\n", pendingPhV7, stdDev);
                Serial.println(F("[CAL-pH] Next: Rinse probe in distilled water, dry gently with lint-free paper,"));
                Serial.println(F("[CAL-pH] place probe into pH 4.01 buffer solution, and run 'ph cal 4.01'."));
            }
        }
    } else if (cmd.equalsIgnoreCase("ph cal 4") || cmd.equalsIgnoreCase("ph cal 4.01") || 
               cmd.equalsIgnoreCase("ph point 4.01") || cmd.equalsIgnoreCase("ph 4") || cmd.equalsIgnoreCase("cal_ph4")) {
        if (!hasPendingPhV7) {
            Serial.println(F("[CAL-pH] ERROR: Please calibrate pH 7.00 reference first ('ph cal 7.00')!"));
            return;
        }

        Serial.println();
        Serial.println(F("[CAL-pH] === STEP 2: pH 4.01 BUFFER CALIBRATION ==="));
        Serial.println(F("[CAL-pH] Submerge rinsed probe into pH 4.01 buffer solution."));
        Serial.println(F("[CAL-pH] Stir gently and hold steady. Sampling 30 readings..."));

        float avgV = 0.0f, stdDev = 0.0f;
        if (phSensor.acquireCalibrationReading(avgV, stdDev)) {
            if (stdDev > 0.050f) {
                Serial.printf("[CAL-pH] WARNING: Voltage unstable (V_avg=%.3fV, σ=%.4fV > 0.050V). Retry 'ph cal 4.01'.\n", avgV, stdDev);
            } else if (avgV < 0.10f || avgV > 4.95f) {
                Serial.printf("[CAL-pH] ERROR: Voltage %.3fV is out of physical circuit limits.\n", avgV);
            } else {
                float deltaV = pendingPhV7 - avgV;
                if (abs(deltaV) < 0.150f) {
                    Serial.printf("[CAL-pH] ERROR: Voltage separation too small (|ΔV|=%.3fV < 0.150V). Buffer depleted or probe fault.\n", abs(deltaV));
                } else {
                    float slope = (7.00f - 4.01f) / deltaV;
                    float intercept = 7.00f - (slope * pendingPhV7);

                    if (abs(slope) < 0.50f || abs(slope) > 12.00f) {
                        Serial.printf("[CAL-pH] ERROR: Calculated slope %.3f pH/V is outside plausible physical range (0.5 to 12.0).\n", slope);
                    } else {
                        pendingPhV4 = avgV;
                        hasPendingPhV4 = true;

                        Serial.println();
                        Serial.println(F("==================== pH CALIBRATION PROPOSAL ===================="));
                        Serial.printf("pH 7.00 Reference Board Voltage : %.3f V\n", pendingPhV7);
                        Serial.printf("pH 4.01 Reference Board Voltage : %.3f V\n", pendingPhV4);
                        Serial.printf("Voltage Separation (|ΔV|)       : %.3f V\n", abs(deltaV));
                        Serial.printf("Calculated Nernstian Slope      : %.3f pH/V\n", slope);
                        Serial.printf("Calculated Intercept            : %.3f\n", intercept);
                        Serial.println(F("Validation Status               : PASSED (Physically Plausible)"));
                        Serial.println(F("================================================================="));
                        Serial.println(F("Type 'ph confirm' to commit to ESP32 Flash NVS, or 'ph cancel' to abort."));
                    }
                }
            }
        }
    } else if (cmd.equalsIgnoreCase("ph confirm")) {
        if (!hasPendingPhV7 || !hasPendingPhV4) {
            Serial.println(F("[CAL-pH] No complete calibration proposal to confirm. Run 'ph cal 7.00' and 'ph cal 4.01' first."));
            return;
        }
        if (phSensor.setCalibration(pendingPhV7, pendingPhV4, true)) {
            Serial.println(F("[CAL-pH] SUCCESS: Two-point calibration COMMITTED to flash NVS."));
            Serial.println(F("[CAL-pH] Live calibrated pH measurements are now ACTIVE."));
            hasPendingPhV7 = false;
            hasPendingPhV4 = false;
        } else {
            Serial.println(F("[CAL-pH] ERROR: Validation failed when saving calibration."));
        }
    } else if (cmd.equalsIgnoreCase("ph cancel")) {
        hasPendingPhV7 = false;
        hasPendingPhV4 = false;
        Serial.println(F("[CAL-pH] Pending pH calibration proposal canceled."));
    } else if (cmd.equalsIgnoreCase("ph reset")) {
        phSensor.resetCalibration();
        hasPendingPhV7 = false;
        hasPendingPhV4 = false;
        Serial.println(F("[CAL-pH] pH sensor RESET. Status reverted to CALIBRATION_PENDING."));
    }
    // --- Turbidity Optical Calibration Workflow ---
    else if (cmd.equalsIgnoreCase("turb cal clear") || cmd.equalsIgnoreCase("turb cal 0") || 
             cmd.equalsIgnoreCase("turb point 0") || cmd.equalsIgnoreCase("cal_turb_clear")) {
        Serial.println();
        Serial.println(F("[CAL-Turb] === STEP 1: 0 NTU CLEAR BASELINE CALIBRATION ==="));
        Serial.println(F("[CAL-Turb] Submerge optical probe in 0 NTU distilled or deionized water."));
        Serial.println(F("[CAL-Turb] Ensure probe is shielded from direct sunlight and container reflections."));
        Serial.println(F("[CAL-Turb] Sampling 30 readings for signal stabilization..."));

        float avgV = 0.0f, stdDev = 0.0f;
        if (turbSensor.acquireCalibrationReading(avgV, stdDev)) {
            if (stdDev > 0.050f) {
                Serial.printf("[CAL-Turb] WARNING: Voltage unstable (V_avg=%.3fV, σ=%.4fV > 0.050V). Check for micro-bubbles.\n", avgV, stdDev);
            } else if (avgV < 2.00f || avgV > 5.00f) {
                Serial.printf("[CAL-Turb] ERROR: Clear baseline voltage %.3fV is below minimum 2.00V.\n", avgV);
                Serial.println(F("[CAL-Turb] In clear water, optical transmission should yield high voltage. Check probe cleanliness."));
            } else {
                pendingTurbVClear = avgV;
                hasPendingTurbClear = true;
                Serial.printf("[CAL-Turb] SUCCESS: 0 NTU Baseline recorded -> V_clear = %.3f V (σ = %.4f V).\n", pendingTurbVClear, stdDev);
                Serial.println(F("[CAL-Turb] Next: Submerge probe into certified NTU standard (e.g. 100 NTU),"));
                Serial.println(F("[CAL-Turb] and run 'turb cal <known_NTU>' (e.g. 'turb cal 100')."));
            }
        }
    } else if (cmd.startsWith("turb cal ") || cmd.startsWith("turb point ")) {
        if (!hasPendingTurbClear) {
            Serial.println(F("[CAL-Turb] ERROR: Please calibrate 0 NTU clear baseline first ('turb cal clear')!"));
            return;
        }

        String ntuStr = cmd.substring(cmd.lastIndexOf(' ') + 1);
        float stdNtu = ntuStr.toFloat();

        if (stdNtu <= 0.0f || stdNtu > 3000.0f) {
            Serial.printf("[CAL-Turb] ERROR: Invalid standard reference NTU: '%.1f'. Must be > 0 and <= 3000 NTU.\n", stdNtu);
            return;
        }

        Serial.println();
        Serial.printf("[CAL-Turb] === STEP 2: %.1f NTU STANDARD CALIBRATION ===\n", stdNtu);
        Serial.println(F("[CAL-Turb] Submerge optical probe into certified turbidity standard."));
        Serial.println(F("[CAL-Turb] Sampling 30 readings for signal stabilization..."));

        float avgV = 0.0f, stdDev = 0.0f;
        if (turbSensor.acquireCalibrationReading(avgV, stdDev)) {
            if (stdDev > 0.050f) {
                Serial.printf("[CAL-Turb] WARNING: Voltage unstable (V_avg=%.3fV, σ=%.4fV > 0.050V).\n", avgV, stdDev);
            } else if (avgV >= pendingTurbVClear) {
                Serial.printf("[CAL-Turb] ERROR: Optical inversion! Standard voltage (%.3fV) >= Clear baseline (%.3fV).\n", 
                              avgV, pendingTurbVClear);
                Serial.println(F("[CAL-Turb] Optical turbidity probes must show reduced voltage as turbidity increases."));
            } else {
                float deltaV = pendingTurbVClear - avgV;
                if (deltaV < 0.150f) {
                    Serial.printf("[CAL-Turb] ERROR: Insufficient optical attenuation (|ΔV|=%.3fV < 0.150V).\n", deltaV);
                } else {
                    pendingTurbVStd = avgV;
                    pendingTurbNtuStd = stdNtu;
                    hasPendingTurbStd = true;

                    Serial.println();
                    Serial.println(F("==================== TURBIDITY CALIBRATION PROPOSAL ===================="));
                    Serial.printf("0 NTU Clear Baseline Voltage    : %.3f V\n", pendingTurbVClear);
                    Serial.printf("Standard Reference (%.1f NTU)   : %.3f V\n", pendingTurbNtuStd, pendingTurbVStd);
                    Serial.printf("Optical Attenuation (ΔV)        : %.3f V\n", deltaV);
                    Serial.println(F("Optical Monotonicity            : VALID (V_standard < V_clear)"));
                    Serial.println(F("Validation Status               : PASSED (Physically Plausible)"));
                    Serial.println(F("========================================================================"));
                    Serial.println(F("Type 'turb confirm' to commit to ESP32 Flash NVS, or 'turb cancel' to abort."));
                }
            }
        }
    } else if (cmd.equalsIgnoreCase("turb confirm")) {
        if (!hasPendingTurbClear || !hasPendingTurbStd) {
            Serial.println(F("[CAL-Turb] No complete turbidity calibration proposal to confirm."));
            return;
        }
        if (turbSensor.setCalibration(pendingTurbVClear, pendingTurbVStd, pendingTurbNtuStd, true)) {
            Serial.println(F("[CAL-Turb] SUCCESS: Turbidity calibration COMMITTED to flash NVS."));
            Serial.println(F("[CAL-Turb] Live calibrated NTU measurements are now ACTIVE."));
            hasPendingTurbClear = false;
            hasPendingTurbStd = false;
        } else {
            Serial.println(F("[CAL-Turb] ERROR: Validation failed when saving calibration."));
        }
    } else if (cmd.equalsIgnoreCase("turb cancel")) {
        hasPendingTurbClear = false;
        hasPendingTurbStd = false;
        Serial.println(F("[CAL-Turb] Pending turbidity calibration proposal canceled."));
    } else if (cmd.equalsIgnoreCase("turb reset")) {
        turbSensor.resetCalibration();
        hasPendingTurbClear = false;
        hasPendingTurbStd = false;
        Serial.println(F("[CAL-Turb] Turbidity sensor RESET. Status reverted to CALIBRATION_PENDING."));
    }
    // --- TDS Calibration Workflow (Direct 3.3V ADC on GPIO35, NO Divider) ---
    else if ([&]() {
        String lower = cmd;
        lower.toLowerCase();
        return lower == "tds cal" || lower.startsWith("tds cal ") || lower.startsWith("tds point ");
    }()) {
        String lower = cmd;
        lower.toLowerCase();
        float stdPpm = 0.0f;
        if (lower.startsWith("tds cal ")) {
            stdPpm = cmd.substring(8).toFloat();
        } else if (lower.startsWith("tds point ")) {
            stdPpm = cmd.substring(10).toFloat();
        }
        if (stdPpm < 10.0f || stdPpm > 3000.0f) {
            Serial.println(F("[CAL-TDS] Specify a known TDS standard solution in ppm (10 - 3000 ppm), e.g. 'tds cal 342' or 'tds cal 707'."));
            return;
        }

        Serial.println();
        Serial.printf("[CAL-TDS] === TDS REFERENCE CALIBRATION (%.0f ppm @ ~25C) ===\n", stdPpm);
        Serial.println(F("[CAL-TDS] Submerge rinsed TDS probe into certified calibration standard solution."));
        Serial.println(F("[CAL-TDS] Stir gently to dislodge bubbles, then hold steady. Sampling 30 readings..."));

        float avgV = 0.0f, stdDev = 0.0f;
        if (tdsSensor.acquireCalibrationReading(avgV, stdDev)) {
            if (stdDev > 0.050f) {
                Serial.printf("[CAL-TDS] WARNING: Voltage unstable (V_adc=%.3fV, σ=%.4fV > 0.050V). Let settle & retry.\n", avgV, stdDev);
            } else if (avgV < 0.10f || avgV > 2.95f) {
                Serial.printf("[CAL-TDS] ERROR: Measured ADC voltage %.3fV out of bounds (0.10V - 2.95V). Check probe immersion/3V3 wiring.\n", avgV);
            } else {
                float rawPoly = TDSSensor::computeRawPolynomialPpm(avgV);
                if (rawPoly < 5.0f) {
                    Serial.println(F("[CAL-TDS] ERROR: Unscaled polynomial reading too small for reliable calibration."));
                } else {
                    float candidateK = stdPpm / rawPoly;
                    float calcTds = rawPoly * candidateK;
                    float relErrPct = (fabs(calcTds - stdPpm) / stdPpm) * 100.0f;
                    if (candidateK < 0.15f || candidateK > 5.00f) {
                        Serial.printf("[CAL-TDS] ERROR: Derived cell constant k=%.3f outside plausible bounds (0.15 - 5.00).\n", candidateK);
                    } else if (isnan(calcTds) || isinf(calcTds) || relErrPct > 5.0f) {
                        Serial.printf("[CAL-TDS] ERROR: Computed TDS %.1f ppm deviates %.2f%% from reference %.1f ppm.\n",
                                      calcTds, relErrPct, stdPpm);
                    } else {
                        pendingTdsVStd = avgV;
                        pendingTdsPpmStd = stdPpm;
                        hasPendingTdsStd = true;

                        Serial.println();
                        Serial.println(F("==================== TDS CALIBRATION PROPOSAL ===================="));
                        Serial.printf("Standard Concentration          : %.1f ppm\n", pendingTdsPpmStd);
                        Serial.printf("Measured ADC Voltage (GPIO35)   : %.3f V (Direct 1.0x, σ=%.4f V)\n", pendingTdsVStd, stdDev);
                        Serial.printf("Unscaled Polynomial Output      : %.1f ppm\n", rawPoly);
                        Serial.printf("Derived Cell Constant (kFactor) : %.4f\n", candidateK);
                        Serial.printf("Proposed Calculated TDS         : %.1f ppm (Error: %.2f%%)\n", calcTds, relErrPct);
                        Serial.println(F("Validation Status               : PASSED (Physically Plausible)"));
                        Serial.println(F("=================================================================="));
                        Serial.println(F("Type 'tds confirm' to commit to ESP32 Flash NVS, or 'tds cancel' to abort."));
                    }
                }
            }
        }
    } else if (cmd.equalsIgnoreCase("tds confirm")) {
        if (!hasPendingTdsStd) {
            Serial.println(F("[CAL-TDS] No pending TDS calibration to confirm. Run 'tds cal <known_ppm>' first."));
            return;
        }
        if (tdsSensor.setCalibrationFromReference(pendingTdsPpmStd, pendingTdsVStd, true)) {
            Serial.println(F("[CAL-TDS] SUCCESS: TDS calibration COMMITTED to flash NVS."));
            Serial.println(F("[CAL-TDS] Live calibrated TDS ppm measurements are now ACTIVE."));
            SensorReading verifyReading = tdsSensor.read();
            tdsReading = verifyReading;
            if (verifyReading.isValid && !isnan(verifyReading.calibratedValue)) {
                float diffPct = ((verifyReading.calibratedValue - pendingTdsPpmStd) / pendingTdsPpmStd) * 100.0f;
                Serial.printf("[CAL-TDS] Live Verification Readback  : %.1f ppm @ %.3f V (Ref: %.1f ppm, Diff: %+.2f%%)\n",
                              verifyReading.calibratedValue, verifyReading.adcVoltage, pendingTdsPpmStd, diffPct);
            } else {
                Serial.printf("[CAL-TDS] WARNING: Post-confirm verification reported '%s' (Vadc=%.3f V).\n",
                              verifyReading.message, verifyReading.adcVoltage);
            }
            hasPendingTdsStd = false;
        } else {
            Serial.println(F("[CAL-TDS] ERROR: Validation failed when saving TDS calibration."));
        }
    } else if (cmd.equalsIgnoreCase("tds cancel")) {
        hasPendingTdsStd = false;
        Serial.println(F("[CAL-TDS] Pending TDS calibration proposal canceled."));
    } else if (cmd.equalsIgnoreCase("tds reset")) {
        tdsSensor.resetCalibration();
        hasPendingTdsStd = false;
        Serial.println(F("[CAL-TDS] TDS sensor RESET. Status reverted to CALIBRATION_PENDING."));
    }
    // --- Dual Water Quality Mode Commands ---
    else if (cmd.equalsIgnoreCase("mode drinking") || cmd.equalsIgnoreCase("mode drink")) {
        sensorValidator.setMode(MODE_DRINKING, true);
        printModeStatus();
    } else if (cmd.equalsIgnoreCase("mode regular") || cmd.equalsIgnoreCase("mode regular_usage") || cmd.equalsIgnoreCase("mode usage")) {
        sensorValidator.setMode(MODE_REGULAR_USAGE, true);
        printModeStatus();
    } else if (cmd.equalsIgnoreCase("mode") || cmd.equalsIgnoreCase("mode status")) {
        printModeStatus();
    }
    // --- Global Calibration Reset ---
    else if (cmd.equalsIgnoreCase("cal reset") || cmd.equalsIgnoreCase("cal_reset")) {
        phSensor.resetCalibration();
        turbSensor.resetCalibration();
        tdsSensor.resetCalibration();
        hasPendingPhV7 = false;
        hasPendingPhV4 = false;
        hasPendingTurbClear = false;
        hasPendingTurbStd = false;
        hasPendingTdsStd = false;
        Serial.println(F("[CAL] ALL sensor calibrations (pH, Turbidity, TDS) RESET to CALIBRATION_PENDING."));
    } else if (cmd.startsWith("demo ")) {
        int val = cmd.substring(5).toInt();
        Serial.printf("[DEMO] Demo simulation flag command received: %d.\n", val);
    } else {
        Serial.printf("[CLI] Unknown command: '%s'. Type 'help' or 'cal help' for available commands.\n", cmd.c_str());
    }
}

void printHelpMenu() {
    Serial.println();
    Serial.println(F("================================================================================"));
    Serial.println(F("         HYDROSENSE — BENCH CALIBRATION, MODE & DIAGNOSTICS CLI MENU           "));
    Serial.println(F("================================================================================"));
    Serial.println(F(" General & Modes:"));
    Serial.println(F("   help / ?        : Show this interactive command menu"));
    Serial.println(F("   status          : Print real-time electrical & sensor diagnostics"));
    Serial.println(F("   net / wifi      : Print Wi-Fi & ThingSpeak telemetry network diagnostics"));
    Serial.println(F("   cal status      : Display stored calibration coefficients & pending bench points"));
    Serial.println(F("   mode status     : Show active water quality mode and thresholds"));
    Serial.println(F("   mode drinking   : Switch to DRINKING MODE (IS 10500: pH 6.5-8.5, <=1NTU, <=500ppm)"));
    Serial.println(F("   mode regular    : Switch to REGULAR USAGE MODE (configurable operational settings)"));
    Serial.println();
    Serial.println(F(" pH Sensor Calibration (GPIO34, 2-Point Buffer: pH 7.00 & pH 4.01):"));
    Serial.println(F("   ph cal 7.00     : Submerge in pH 7.00 buffer -> records stable V_pH7"));
    Serial.println(F("   ph cal 4.01     : Rinse, dry, submerge in pH 4.01 buffer -> records V_pH4 & slope"));
    Serial.println(F("   ph confirm      : Save pH calibration to ESP32 Flash NVS (or 'ph cancel'/'ph reset')"));
    Serial.println();
    Serial.println(F(" Turbidity Sensor Calibration (GPIO32, 0 NTU Baseline & Known Standard):"));
    Serial.println(F("   turb cal clear  : Submerge in 0 NTU distilled water -> records V_clear baseline"));
    Serial.println(F("   turb cal <NTU>  : Submerge in known standard (e.g. 'turb cal 100') -> records V_std"));
    Serial.println(F("   turb confirm    : Save turbidity calibration to ESP32 Flash NVS (or 'turb cancel'/'turb reset')"));
    Serial.println();
    Serial.println(F(" TDS Sensor Calibration (GPIO35, Direct 3.3V ADC, Known Standard ppm):"));
    Serial.println(F("   tds cal <ppm>   : Submerge in known standard (e.g. 'tds cal 342') -> computes kFactor"));
    Serial.println(F("   tds confirm     : Save TDS calibration to ESP32 Flash NVS (or 'tds cancel'/'tds reset')"));
    Serial.println();
    Serial.println(F(" Global Reset:"));
    Serial.println(F("   cal reset       : Revert pH, Turbidity & TDS back to CALIBRATION_PENDING"));
    Serial.println(F("================================================================================"));
    Serial.println();
}

void printModeStatus() {
    const ModeThresholds& th = sensorValidator.getActiveThresholds();
    Serial.println();
    Serial.println(F("==================== WATER QUALITY MODE STATUS ===================="));
    Serial.printf("Active Mode         : %s\n", sensorValidator.getModeName());
    Serial.printf("Reference Profile   : %s\n",
                  sensorValidator.getMode() == MODE_DRINKING
                      ? "BIS IS 10500:2012 Acceptable Limits"
                      : "User-Configurable Non-Drinking Operational Settings");
    Serial.printf("pH Allowed Range    : %.2f - %.2f\n", th.phMin, th.phMax);
    Serial.printf("Turbidity Limit     : <= %.2f NTU\n", th.turbMax);
    Serial.printf("TDS Limit           : <= %.0f ppm\n", th.tdsMax);
    Serial.printf("Buzzer Armed State  : %s\n",
                  sensorValidator.shouldSoundBuzzer() ? "ALARMING (Calibrated Violation)" : "SILENT (No Valid Violation)");
    Serial.println(F("==================================================================="));
    Serial.println();
}

void printCalibrationStatus() {
    Serial.println();
    Serial.println(F("==================== SENSOR CALIBRATION STATUS ===================="));
    Serial.println(F("--- [1] pH Sensor (E201-C on GPIO34, 15k/10k Divider) ---"));
    Serial.printf("Status              : %s\n", phSensor.isCalibrated() ? "TWO-POINT CALIBRATED" : "CALIBRATION PENDING");
    Serial.printf("Current Voltage     : V_board=%.3f V | V_adc=%.3f V\n", phReading.reconstructedVoltage, phReading.adcVoltage);
    if (phSensor.isCalibrated()) {
        Serial.printf("Reference V_pH 7.00 : %.3f V\n", phSensor.getVPh7());
        Serial.printf("Reference V_pH 4.01 : %.3f V\n", phSensor.getVPh4());
        Serial.printf("Nernstian Slope     : %.3f pH/V (Intercept: %.3f)\n", phSensor.getSlope(), phSensor.getIntercept());
    }
    if (hasPendingPhV7) {
        Serial.printf("Bench Staging       : V_pH7=%.3fV%s\n", pendingPhV7,
                      hasPendingPhV4 ? " | V_pH4 recorded -> type 'ph confirm'" : " | awaiting 'ph cal 4.01'");
    }

    Serial.println();
    Serial.println(F("--- [2] Turbidity Sensor (Optical on GPIO32, 15k/10k Divider) ---"));
    Serial.printf("Status              : %s\n", turbSensor.isCalibrated() ? "CALIBRATED" : "CALIBRATION PENDING");
    Serial.printf("Current Voltage     : V_board=%.3f V | V_adc=%.3f V\n", turbReading.reconstructedVoltage, turbReading.adcVoltage);
    if (turbSensor.isCalibrated()) {
        Serial.printf("Clear (0 NTU)       : %.3f V | Standard (%.1f NTU): %.3f V\n",
                      turbSensor.getVClear(), turbSensor.getNtuStandard(), turbSensor.getVStandard());
    }
    if (hasPendingTurbClear) {
        Serial.printf("Bench Staging       : V_clear=%.3fV%s\n", pendingTurbVClear,
                      hasPendingTurbStd ? " | V_std recorded -> type 'turb confirm'" : " | awaiting 'turb cal <ntu>'");
    }

    Serial.println();
    Serial.println(F("--- [3] TDS Sensor (Direct 3.3V ADC on GPIO35, NO Divider) ---"));
    Serial.printf("Status              : %s\n", tdsSensor.isCalibrated() ? "CALIBRATED" : "CALIBRATION PENDING");
    Serial.printf("Current ADC Voltage : %.3f V (Direct 1.0x)\n", tdsReading.adcVoltage);
    if (tdsSensor.isCalibrated()) {
        Serial.printf("Calibrated kFactor  : %.4f (Ref %.0f ppm @ %.3f V)\n",
                      tdsSensor.getKFactor(), tdsSensor.getPpmStandard(), tdsSensor.getVStandard());
        if (!isnan(tdsReading.calibratedValue)) {
            Serial.printf("Live TDS Reading    : %.1f ppm\n", tdsReading.calibratedValue);
        }
    }
    if (hasPendingTdsStd) {
        Serial.printf("Bench Staging       : %.1f ppm @ %.3fV recorded -> type 'tds confirm'\n",
                      pendingTdsPpmStd, pendingTdsVStd);
    }
    Serial.println(F("==================================================================="));
    Serial.println();
}

void printDiagnostics() {
    Serial.println();
    Serial.println(F("==================== SYSTEM DIAGNOSTICS ===================="));
    Serial.printf("Water Quality Mode        : %s\n", sensorValidator.getModeName());
    Serial.printf("pH Sensor (GPIO34)        : Raw=%0.1f | Vadc=%.3f V | Vboard=%.3f V | Status=%s\n",
                  phReading.rawAdc, phReading.adcVoltage, phReading.reconstructedVoltage, phReading.message);
    Serial.printf("Turbidity Sensor (GPIO32) : Raw=%0.1f | Vadc=%.3f V | Vboard=%.3f V | Status=%s\n",
                  turbReading.rawAdc, turbReading.adcVoltage, turbReading.reconstructedVoltage, turbReading.message);
    Serial.printf("TDS Sensor (GPIO35)       : Raw=%0.1f | Vadc=%.3f V (Direct 1.0x) | Status=%s\n",
                  tdsReading.rawAdc, tdsReading.adcVoltage, tdsReading.message);
    Serial.printf("System Severity           : %s (%d) | Buzzer: %s\n",
                  sensorValidator.getSeverityName(), (int)sensorValidator.getSeverity(),
                  sensorValidator.shouldSoundBuzzer() ? "ACTIVE" : "SILENT");
    Serial.printf("Alert Explanation         : %s\n", sensorValidator.getAlertMessage());
    Serial.printf("System Health Bitmask     : 0x%04X\n", sensorValidator.getHealthCode());
    Serial.printf("Wi-Fi Connected           : %s\n", cloudManager.isWifiConnected() ? "YES" : "NO");
    Serial.printf("Cloud Telemetry Status    : %s\n", cloudManager.getStatusText());
    Serial.println(F("============================================================"));
    Serial.println();
}
