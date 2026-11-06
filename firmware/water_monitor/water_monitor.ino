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

    // 4. Initialize Sensors
    phSensor.begin();
    turbSensor.begin();
    tdsSensor.begin();
    Serial.println(F("[SETUP] pH Sensor initialized on GPIO34 (ADC1_CH6)."));
    Serial.println(F("[SETUP] Turbidity Sensor initialized on GPIO32 (ADC1_CH4)."));
    Serial.printf("[SETUP] TDS Sensor on GPIO35: %s\n", 
                  tdsSensor.isAvailable() ? "ENABLED" : "RESERVED/PENDING (Disabled)");

    // 5. Initialize Wi-Fi & Cloud Manager
    cloudManager.begin();

    // 6. Print Initial Electrical Safety Verification
    Serial.println(F("----------------------------------------------------------"));
    Serial.println(F("ELECTRICAL SAFETY REMINDER:"));
    Serial.println(F("Verify with a multimeter that divider junction voltages"));
    Serial.println(F("never exceed 3.0V at GPIO32 and GPIO34."));
    Serial.println(F("Type 'help' in Serial Monitor for interactive calibration."));
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

        // Evaluate system invariants, safety, and alert severity
        bool isWifi = cloudManager.isWifiConnected();
        bool isCloudOk = (strcmp(cloudManager.getStatusText(), "SYNC") == 0 || 
                          strcmp(cloudManager.getStatusText(), "IDLE") == 0);

        sensorValidator.evaluate(phReading, turbReading, tdsReading, isWifi, isCloudOk);
    }

    // 2. Update Alert Manager State Machine (Acoustic buzzer patterns)
    alertManager.update(currentMillis, sensorValidator.getSeverity());

    // 3. Update OLED Display Manager (Non-blocking screen refresh & rotation)
    displayManager.update(currentMillis, 
                          phReading, 
                          turbReading, 
                          tdsReading, 
                          sensorValidator, 
                          cloudManager.isWifiConnected(), 
                          cloudManager.getStatusText());

    // 4. Update Cloud Telemetry Manager (ThingSpeak HTTP POST every 20s)
    cloudManager.update(currentMillis, 
                        phReading, 
                        turbReading, 
                        tdsReading, 
                        sensorValidator);

    // 5. Periodic Diagnostics to Serial (Every 2 seconds)
    if (currentMillis - lastSerialLogMillis >= 2000) {
        lastSerialLogMillis = currentMillis;

        Serial.printf("[TELEMETRY] pH: %s | Turb: %s | TDS: %s | Sev: %s | Health: 0x%04X | Net: %s\n",
                      phReading.isValid ? (String(phReading.calibratedValue, 2) + " pH").c_str() : phReading.message,
                      turbReading.isValid ? (String(turbReading.calibratedValue, 1) + " NTU").c_str() : turbReading.message,
                      tdsReading.isValid ? (String(tdsReading.calibratedValue, 0) + " ppm").c_str() : "N/A",
                      sensorValidator.getSeverityName(),
                      sensorValidator.getHealthCode(),
                      cloudManager.getStatusText());

        // Highlight any electrical safety alarm
        if (phReading.status == STATUS_OVER_RANGE || turbReading.status == STATUS_OVER_RANGE) {
            Serial.println(F("[SAFETY ALARM] ELECTRICAL OVER-RANGE DETECTED! ADC > 3.05V! Check divider wiring!"));
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

    if (cmd.equalsIgnoreCase("help") || cmd.equalsIgnoreCase("?")) {
        printHelpMenu();
    } else if (cmd.equalsIgnoreCase("status")) {
        printDiagnostics();
    } else if (cmd.equalsIgnoreCase("cal_ph7")) {
        // Calibrate pH 7.00 buffer using current measured board voltage
        Serial.printf("[CAL] Calibrating pH 7.00 with current board voltage: %.3f V\n", phReading.reconstructedVoltage);
        // Temporary 2-point default assumption until pH 4 is supplied
        phSensor.setCalibration(phReading.reconstructedVoltage, phReading.reconstructedVoltage - 1.25f);
        Serial.println(F("[CAL] pH 7.00 point saved. Now place probe in pH 4.01 buffer and run 'cal_ph4'."));
    } else if (cmd.equalsIgnoreCase("cal_ph4")) {
        // Use stored or active board voltage for pH 4.01
        Serial.printf("[CAL] Calibrating pH 4.01 with current board voltage: %.3f V\n", phReading.reconstructedVoltage);
        // Update calibration
        phSensor.setCalibration(phReading.reconstructedVoltage + 1.25f, phReading.reconstructedVoltage);
        Serial.println(F("[CAL] pH calibration complete. Live readings enabled."));
    } else if (cmd.equalsIgnoreCase("cal_turb_clear")) {
        Serial.printf("[CAL] Setting Turbidity CLEAR baseline (0 NTU) to: %.3f V\n", turbReading.reconstructedVoltage);
        turbSensor.setCalibration(turbReading.reconstructedVoltage, turbReading.reconstructedVoltage - 1.5f, 100.0f);
        Serial.println(F("[CAL] Turbidity baseline saved."));
    } else if (cmd.equalsIgnoreCase("cal_reset")) {
        phSensor.resetCalibration();
        turbSensor.resetCalibration();
        Serial.println(F("[CAL] All calibration coefficients reset to CALIBRATION_PENDING."));
    } else if (cmd.startsWith("demo ")) {
        int val = cmd.substring(5).toInt();
        Serial.printf("[DEMO] Demo simulation flag command received: %d (Recompile with FEATURE_DEMO_MODE for persistent demo).\n", val);
    } else {
        Serial.printf("[CLI] Unknown command: '%s'. Type 'help' for available commands.\n", cmd.c_str());
    }
}

void printHelpMenu() {
    Serial.println();
    Serial.println(F("=========================================================="));
    Serial.println(F("         SERIAL INTERACTIVE CALIBRATION COMMANDS          "));
    Serial.println(F("=========================================================="));
    Serial.println(F(" help            : Show this command menu"));
    Serial.println(F(" status          : Print comprehensive electrical diagnostics"));
    Serial.println(F(" cal_ph7         : Set current pH probe voltage as pH 7.00 buffer"));
    Serial.println(F(" cal_ph4         : Set current pH probe voltage as pH 4.01 buffer"));
    Serial.println(F(" cal_turb_clear  : Set current turbidity probe as clear (0 NTU)"));
    Serial.println(F(" cal_reset       : Reset calibrations back to pending state"));
    Serial.println(F("=========================================================="));
    Serial.println();
}

void printDiagnostics() {
    Serial.println();
    Serial.println(F("==================== SYSTEM DIAGNOSTICS ===================="));
    Serial.printf("pH Sensor (GPIO34)        : Raw=%0.1f | Vadc=%.3f V | Vboard=%.3f V | Status=%s\n",
                  phReading.rawAdc, phReading.adcVoltage, phReading.reconstructedVoltage, phReading.message);
    Serial.printf("Turbidity Sensor (GPIO32) : Raw=%0.1f | Vadc=%.3f V | Vboard=%.3f V | Status=%s\n",
                  turbReading.rawAdc, turbReading.adcVoltage, turbReading.reconstructedVoltage, turbReading.message);
    Serial.printf("TDS Sensor (GPIO35)       : %s\n", 
                  tdsReading.isValid ? (String(tdsReading.calibratedValue, 1) + " ppm").c_str() : "N/A (Pending Installation)");
    Serial.printf("System Severity           : %s (%d)\n", sensorValidator.getSeverityName(), (int)sensorValidator.getSeverity());
    Serial.printf("System Health Bitmask     : 0x%04X\n", sensorValidator.getHealthCode());
    Serial.printf("Wi-Fi Connected           : %s\n", cloudManager.isWifiConnected() ? "YES" : "NO");
    Serial.printf("Cloud Telemetry Status    : %s\n", cloudManager.getStatusText());
    Serial.println(F("============================================================"));
    Serial.println();
}
