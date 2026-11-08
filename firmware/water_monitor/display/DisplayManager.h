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
        AlertSeverity sev = validator.getSeverity();

        // Header Bar
        if (sev >= SEVERITY_WARNING && _flashState) {
            // Inverted header to catch attention during alert
            _display.fillRect(0, 0, 128, 12, SSD1306_WHITE);
            _display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
            _display.setTextSize(1);
            _display.setCursor(4, 2);
            _display.print(validator.getAlertMessage());
            _display.setTextColor(SSD1306_WHITE);
        } else {
            _display.setTextSize(1);
            _display.setCursor(0, 0);
            _display.print(F("AQUA-MONITOR"));
            _display.setCursor(92, 0);
            _display.printf("[%s]", validator.getSeverityName());
            _display.drawLine(0, 10, 127, 10, SSD1306_WHITE);
        }

        // 1. pH Reading
        _display.setCursor(0, 14);
        _display.print(F("pH  : "));
        if (ph.status == STATUS_OVER_RANGE) {
            _display.print(F("OVER-RANGE!"));
        } else if (ph.status == STATUS_DISCONNECTED) {
            _display.print(F("DISCONNECTED"));
        } else if (ph.status == STATUS_CALIBRATION_PENDING || isnan(ph.calibratedValue)) {
            _display.printf("CAL PEND (%.2fV)", ph.reconstructedVoltage);
        } else if (ph.isValid) {
            _display.printf("%.2f (%.2fV)", ph.calibratedValue, ph.reconstructedVoltage);
            if (ph.status == STATUS_WARNING || ph.status == STATUS_CRITICAL) {
                _display.print(F("!"));
            }
        } else {
            _display.print(F("FAULT"));
        }

        // 2. Turbidity Reading
        _display.setCursor(0, 26);
        _display.print(F("Turb: "));
        if (turb.status == STATUS_OVER_RANGE) {
            _display.print(F("OVER-RANGE!"));
        } else if (turb.status == STATUS_DISCONNECTED) {
            _display.print(F("DISCONNECTED"));
        } else if (turb.status == STATUS_CALIBRATION_PENDING || isnan(turb.calibratedValue)) {
            _display.printf("CAL PEND (%.2fV)", turb.reconstructedVoltage);
        } else if (turb.isValid) {
            _display.printf("%.1fNTU (%.2fV)", turb.calibratedValue, turb.reconstructedVoltage);
        } else {
            _display.print(F("FAULT"));
        }

        // 3. TDS Reading (Mandatory: Always N/A until physically installed)
        _display.setCursor(0, 38);
        _display.print(F("TDS : "));
        if (!tds.isValid || tds.status == STATUS_UNAVAILABLE) {
            _display.print(F("N/A (PENDING)"));
        } else {
            _display.printf("%.0f ppm", tds.calibratedValue);
        }

        // Bottom Status Bar
        _display.drawLine(0, 50, 127, 50, SSD1306_WHITE);
        _display.setCursor(0, 54);
        _display.printf("WiFi:%s | Cld:%s", wifiConnected ? "OK" : "NO", cloudStatus);
    }

    /**
     * PAGE 1: Electrical & Voltage Diagnostics
     */
    void renderDiagnostics(const SensorReading& ph, 
                          const SensorReading& turb, 
                          const SensorReading& tds, 
                          const SensorValidator& validator,
                          bool wifiConnected,
                          const char* cloudStatus) {
        // Header
        _display.setTextSize(1);
        _display.setCursor(0, 0);
        _display.print(F("ELECTRICAL DIAGNOSTICS"));
        _display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

        // pH Electrical
        _display.setCursor(0, 14);
        _display.printf("pH  ADC:%.3fV (Vin:%.2f)", ph.adcVoltage, ph.reconstructedVoltage);

        // Turbidity Electrical
        _display.setCursor(0, 26);
        _display.printf("Turb ADC:%.3fV (Vin:%.2f)", turb.adcVoltage, turb.reconstructedVoltage);

        // Safety Status
        _display.setCursor(0, 38);
        if (ph.adcVoltage >= ADC_OVER_RANGE_VOLTS || turb.adcVoltage >= ADC_OVER_RANGE_VOLTS) {
            _display.print(F("SAFETY: DANGER (>3.05V)"));
        } else {
            _display.print(F("SAFETY: SAFE (<3.0V)"));
        }

        // Health Code Bitmask
        _display.drawLine(0, 50, 127, 50, SSD1306_WHITE);
        _display.setCursor(0, 54);
        _display.printf("Health:0x%04X | P:1/2", validator.getHealthCode());
    }
};
