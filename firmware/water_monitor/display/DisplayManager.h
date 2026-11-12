#pragma once

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "../config.h"
#include "../sensors/SensorBase.h"
#include "../sensors/SensorValidator.h"

/**
 * ============================================================================
 * OLED DISPLAY MANAGER (SSD1306 128x64 I2C)
 * ============================================================================
 * Address: 0x3C
 * Pins: SDA = GPIO21, SCL = GPIO22
 * 
 * Features:
 * - Rotating diagnostic pages (Main Monitor vs Electrical Diagnostics)
 * - Prominent warning banner when alerts are active
 * - Displays "CAL PEND" instead of fake numbers when uncalibrated
 * - Displays "TDS: N/A" (never 0 ppm)
 * - Non-blocking refresh and page rotation
 * ============================================================================
 */

class DisplayManager {
public:
    DisplayManager() 
        : _display(OLED_SCREEN_WIDTH, OLED_SCREEN_HEIGHT, &Wire, OLED_RESET_PIN),
          _isInitialized(false),
          _lastRefreshMillis(0),
          _lastPageRotateMillis(0),
          _currentPage(0),
          _flashState(false) {}

    bool begin() {
        Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL);
        if (!_display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDRESS)) {
            Serial.println(F("[DISPLAY] ERROR: SSD1306 initialization failed!"));
            _isInitialized = false;
            return false;
        }

        _isInitialized = true;
        _display.clearDisplay();
        _display.setTextColor(SSD1306_WHITE);

        // Startup Splash Screen
        _display.setTextSize(1);
        _display.setCursor(14, 10);
        _display.println(F("SMART WATER MON"));
        _display.setCursor(20, 26);
        _display.println(F("AI IOT SYSTEM"));
        _display.setCursor(16, 42);
        _display.println(F("Phase 1 - ESP32"));
        _display.drawLine(0, 56, 127, 56, SSD1306_WHITE);
        _display.display();
        delay(1200); // Only initial startup splash uses brief delay

        return true;
    }

    void update(uint32_t currentMillis, 
                const SensorReading& ph, 
                const SensorReading& turb, 
                const SensorReading& tds, 
                const SensorValidator& validator,
                bool wifiConnected,
                const char* cloudStatus) {
        if (!_isInitialized) return;

        // Check non-blocking page rotation
        if (currentMillis - _lastPageRotateMillis >= OLED_PAGE_ROTATE_MS) {
            _lastPageRotateMillis = currentMillis;
            _currentPage = (_currentPage + 1) % 2;
        }

        // Check non-blocking display refresh
        if (currentMillis - _lastRefreshMillis >= OLED_REFRESH_INTERVAL_MS) {
            _lastRefreshMillis = currentMillis;
            _flashState = !_flashState;

            _display.clearDisplay();

            if (_currentPage == 0) {
                renderDashboard(ph, turb, tds, validator, wifiConnected, cloudStatus);
            } else {
                renderDiagnostics(ph, turb, tds, validator, wifiConnected, cloudStatus);
            }

            _display.display();
        }
    }

private:
    Adafruit_SSD1306 _display;
    bool _isInitialized;
    uint32_t _lastRefreshMillis;
    uint32_t _lastPageRotateMillis;
    uint8_t _currentPage;
    bool _flashState;

    /**
     * PAGE 0: Primary Dashboard
     */
    void renderDashboard(const SensorReading& ph, 
                         const SensorReading& turb, 
                         const SensorReading& tds, 
                         const SensorValidator& validator,
                         bool wifiConnected,
                         const char* cloudStatus) {
        bool anyUncalibrated = (
            ph.status == STATUS_CALIBRATION_PENDING ||
            turb.status == STATUS_CALIBRATION_PENDING ||
            tds.status == STATUS_CALIBRATION_PENDING
        );
        AlertSeverity sev = validator.getSeverity();
        const char* statusTag = validator.getWaterStatusLabel();
        if (validator.isCriticalHazard()) {
            statusTag = "HAZARD!";
        } else if (anyUncalibrated && sev == SEVERITY_NORMAL) {
            statusTag = "CAL";
        } else if (tds.status == STATUS_DRY_OR_NOT_IMMERSED && sev == SEVERITY_NORMAL) {
            statusTag = "DRY";
        }

        // Header Bar (flashing inverted bar during warning/critical/hazard)
        if ((sev >= SEVERITY_WARNING || validator.isCriticalHazard()) && _flashState) {
            _display.fillRect(0, 0, 128, 11, SSD1306_WHITE);
            _display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
            _display.setTextSize(1);
            _display.setCursor(2, 2);
            _display.printf("%.20s", validator.getAlertMessage());
            _display.setTextColor(SSD1306_WHITE);
        } else {
            _display.setTextSize(1);
            _display.setCursor(0, 1);
            _display.printf("HYDRO[%s]", validator.getModeShortTag());
            _display.setCursor(74, 1);
            _display.printf("[%s]", statusTag);
            _display.drawLine(0, 10, 127, 10, SSD1306_WHITE);
        }

        // 1. pH Reading
        _display.setCursor(0, 13);
        _display.print(F("pH  :"));
        if (ph.status == STATUS_OVER_RANGE) {
            _display.print(F("OVER-RANGE!"));
        } else if (ph.status == STATUS_DISCONNECTED) {
            _display.print(F("FAULT/0V"));
        } else if (ph.status == STATUS_OUT_OF_CAL_RANGE) {
            _display.printf("OUT-RNG(%.2fV)", ph.reconstructedVoltage);
        } else if (ph.status == STATUS_CALIBRATION_PENDING || isnan(ph.calibratedValue)) {
            _display.print(F("--"));
        } else if (ph.isValid) {
            _display.printf("%.2f%s", ph.calibratedValue,
                            validator.isPhViolated() ? "!" : "");
        } else {
            _display.print(F("FAULT"));
        }

        // 2. Turbidity Reading
        _display.setCursor(0, 22);
        _display.print(F("Turb:"));
        if (turb.status == STATUS_OVER_RANGE) {
            _display.print(F("OVER-RANGE!"));
        } else if (turb.status == STATUS_DISCONNECTED) {
            _display.print(F("FAULT/0V"));
        } else if (turb.status == STATUS_OUT_OF_CAL_RANGE) {
            _display.printf("OUT-RNG!(%.2fV)", turb.reconstructedVoltage);
        } else if (turb.status == STATUS_CALIBRATION_PENDING || isnan(turb.calibratedValue)) {
            _display.printf("UNCAL (%.2fV)", turb.reconstructedVoltage);
        } else if (turb.isValid) {
            _display.printf("%.1fNTU(%.2fV)%s", turb.calibratedValue, turb.reconstructedVoltage,
                            validator.isTurbViolated() ? "!" : "");
        } else {
            _display.print(F("FAULT"));
        }

        // 3. TDS Reading (Direct 3.3V ADC)
        _display.setCursor(0, 31);
        _display.print(F("TDS :"));
        if (tds.status == STATUS_UNAVAILABLE) {
            _display.print(F("N/A (DISABLED)"));
        } else if (tds.status == STATUS_OVER_RANGE) {
            _display.print(F("OVER-RANGE!"));
        } else if (tds.status == STATUS_DISCONNECTED) {
            _display.printf("FAULT (%.2fV)", tds.adcVoltage);
        } else if (tds.status == STATUS_DRY_OR_NOT_IMMERSED) {
            _display.printf("DRY (%.2fV)", tds.adcVoltage);
        } else if (tds.status == STATUS_CALIBRATION_PENDING || isnan(tds.calibratedValue)) {
            _display.printf("UNCAL (%.2fV)", tds.adcVoltage);
        } else if (tds.isValid) {
            _display.printf("%.0fppm(%.2fV)%s", tds.calibratedValue, tds.adcVoltage,
                            validator.isTdsViolated() ? "!" : "");
        } else {
            _display.print(F("FAULT"));
        }

        // 4. Water Quality Score (WQS) & Overall Status
        _display.setCursor(0, 40);
        if (validator.isWqsValid()) {
            _display.printf("WQS :%.1f [%s]", validator.getWqs(), statusTag);
        } else if (validator.isCriticalHazard()) {
            _display.printf("WQS :<=20 [%s]", statusTag);
        } else {
            _display.printf("WQS :N/A [%s]", statusTag);
        }

        // Bottom Status Bar
        _display.drawLine(0, 50, 127, 50, SSD1306_WHITE);
        _display.setCursor(0, 54);
        _display.printf("WiFi:%s | Cld:%s", wifiConnected ? "OK" : "NO", cloudStatus);
    }

    /**
     * PAGE 1: Electrical, Sub-Index & Voltage Diagnostics
     */
    void renderDiagnostics(const SensorReading& ph, 
                          const SensorReading& turb, 
                          const SensorReading& tds, 
                          const SensorValidator& validator,
                          bool wifiConnected,
                          const char* cloudStatus) {
        // Header
        _display.setTextSize(1);
        _display.setCursor(0, 1);
        _display.printf("DIAG [%s]      P2/2", validator.getModeShortTag());
        _display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

        // pH Electrical
        _display.setCursor(0, 13);
        _display.printf("pH :%.2f->%.2fV q:%s", ph.adcVoltage, ph.reconstructedVoltage,
                        isnan(validator.getSubIndexPh()) ? "--" : String(validator.getSubIndexPh(), 0).c_str());

        // Turbidity Electrical
        _display.setCursor(0, 22);
        _display.printf("Tb :%.2f->%.2fV q:%s", turb.adcVoltage, turb.reconstructedVoltage,
                        isnan(validator.getSubIndexTurb()) ? "--" : String(validator.getSubIndexTurb(), 0).c_str());

        // TDS Electrical (Direct 3.3V - No Divider)
        _display.setCursor(0, 31);
        _display.printf("TDS:%.2fV(1x)   q:%s", tds.adcVoltage,
                        isnan(validator.getSubIndexTds()) ? "--" : String(validator.getSubIndexTds(), 0).c_str());

        // Water Status Code
        _display.setCursor(0, 40);
        _display.printf("St:%d (%s)", validator.getWaterStatusCode(), validator.getWaterStatusLabel());

        // Safety & Health Code Bitmask
        bool hazard = (ph.adcVoltage >= ADC_OVER_RANGE_VOLTS ||
                       turb.adcVoltage >= ADC_OVER_RANGE_VOLTS ||
                       tds.adcVoltage >= ADC_OVER_RANGE_VOLTS);
        _display.drawLine(0, 50, 127, 50, SSD1306_WHITE);
        _display.setCursor(0, 54);
        _display.printf("H:0x%04X | %s", validator.getHealthCode(), hazard ? "ADC DANGER!" : "ADC SAFE");
    }
};
