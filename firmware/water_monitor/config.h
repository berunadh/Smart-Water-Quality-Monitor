#pragma once

#include <Arduino.h>

/**
 * ============================================================================
 * SMART APARTMENT WATER QUALITY MONITOR - FIRMWARE CONFIGURATION (PHASE 1)
 * ============================================================================
 * 
 * Target Microcontroller: ESP32 Dev Module (ESP32-D0WD-V3)
 * Arduino Core: Classic ESP32 Arduino Core
 * 
 * IMPORTANT SAFETY AND HARDWARE NOTES:
 * 1. ADC1 pins (GPIO 32, 34, 35) are strictly used. ADC2 is never used
 *    for analog sensing because ADC2 is shared with the Wi-Fi subsystem.
 * 2. Voltage dividers (15kΩ / 10kΩ) reduce 0-5V sensor board outputs to 
 *    0-2.0V safe range for ESP32 ADC (ratio = 0.400).
 * 3. Never allow ADC pin voltage to exceed 3.3V (absolute max 3.6V).
 * ============================================================================
 */

// ----------------------------------------------------------------------------
// 1. PIN ASSIGNMENTS
// ----------------------------------------------------------------------------
#define PIN_PH_ADC          34    // ADC1_CH6: pH Sensor (P pin via 15k/10k divider)
#define PIN_TURBIDITY_ADC   32    // ADC1_CH4: Turbidity Sensor (OUT via 15k/10k divider)
#define PIN_TDS_ADC         35    // ADC1_CH7: Reserved for future TDS (input-only)
#define PIN_OLED_SDA        21    // I2C SDA for SSD1306 OLED
#define PIN_OLED_SCL        22    // I2C SCL for SSD1306 OLED
#define PIN_BUZZER          25    // Module 'S' pin: Active/Passive Buzzer

// ----------------------------------------------------------------------------
// 2. HARDWARE FEATURE FLAGS
// ----------------------------------------------------------------------------
// TDS sensor is now physically installed on GPIO35 (3.3V powered, no divider).
// Uncalibrated TDS must still report NULL/NAN, NEVER 0.0 or raw voltage as ppm.
#define FEATURE_TDS_ENABLED   true

// Demo/Simulation mode: Set to true if testing on a desk without physical probes.
// Simulates normal water values, occasional turbidity spikes, and safe voltages.
#define FEATURE_DEMO_MODE     false

// Buzzer active-low flag (depends on transistor driver module: true for active-low)
#define BUZZER_ACTIVE_LOW     false

// ----------------------------------------------------------------------------
// 3. ELECTRICAL & ADC SPECIFICATIONS
// ----------------------------------------------------------------------------
#define ESP32_ADC_RESOLUTION_BITS   12
#define ESP32_ADC_MAX_RAW           4095.0f
#define ESP32_ADC_VREF              3.30f     // Nominal VDD reference

// Voltage Divider (pH & Turbidity ONLY): R1 = 15kΩ (high-side), R2 = 10kΩ (low-side to GND)
// V_ADC = V_sensor * (R2 / (R1 + R2)) = V_sensor * (10 / 25) = V_sensor * 0.400
// V_sensor = V_ADC / 0.400 = V_ADC * 2.500
#define DIVIDER_R1_OHMS             15000.0f
#define DIVIDER_R2_OHMS             10000.0f
#define VOLTAGE_DIVIDER_RATIO       (DIVIDER_R2_OHMS / (DIVIDER_R1_OHMS + DIVIDER_R2_OHMS)) // 0.40f
#define VOLTAGE_RECONSTRUCT_FACTOR  (1.0f / VOLTAGE_DIVIDER_RATIO)                         // 2.50f

// TDS Direct Connection (NO voltage divider: V_module == V_ADC)
#define TDS_VOLTAGE_MULTIPLIER      1.00f

// Safety & Over-Range Detection Thresholds
// 11dB attenuation saturates around 3.1V - 3.2V.
// Any ADC reading >= 3.05V or raw >= 4000 indicates severe electrical hazard or miswiring!
#define ADC_OVER_RANGE_VOLTS        3.05f
#define ADC_OVER_RANGE_RAW          4000
#define ADC_DISCONNECTED_VOLTS      0.08f     // pH/Turbidity floating or pulled to GND
#define ADC_TDS_DISCONNECTED_VOLTS  0.015f    // TDS open-circuit or dry in air (<15 mV)

// Oversampling and Filter settings
#define ADC_OVERSAMPLE_SAMPLES      25        // Number of samples per reading
#define ADC_SAMPLE_DELAY_MS         3         // Milliseconds between oversamples
#define ADC_TRIM_PERCENT            20        // Drop top/bottom 20% (trimmed mean)

// ----------------------------------------------------------------------------
// 4. OLED DISPLAY CONFIGURATION
// ----------------------------------------------------------------------------
#define OLED_SCREEN_WIDTH           128
#define OLED_SCREEN_HEIGHT          64
#define OLED_I2C_ADDRESS            0x3C
#define OLED_RESET_PIN              -1        // Shared with ESP32 reset

// ----------------------------------------------------------------------------
// 5. TIMING AND NON-BLOCKING SCHEDULING (MILLISECONDS)
// ----------------------------------------------------------------------------
#define SENSOR_SAMPLE_INTERVAL_MS   1000      // Read sensors every 1.0 s
#define OLED_REFRESH_INTERVAL_MS    500       // Refresh OLED every 500 ms
#define OLED_PAGE_ROTATE_MS         4500      // Rotate diagnostic pages every 4.5 s
#define THINGSPEAK_INTERVAL_MS      20000     // 20 s (ThingSpeak free limit is 15s)
#define BUZZER_COOLDOWN_MS          30000     // 30 s mute period after prolonged alarm
#define BUZZER_MAX_ALARM_MS         10000     // Buzzer sounds max 10 s continuously

// ----------------------------------------------------------------------------
// 6. DUAL WATER QUALITY MODES & THRESHOLD PROFILES
// ----------------------------------------------------------------------------
enum WaterQualityMode {
    MODE_DRINKING      = 0,  // Indian Standard IS 10500:2012 Acceptable Limits
    MODE_REGULAR_USAGE = 1   // Configurable non-drinking operational settings
};

// Profile A: DRINKING MODE (BIS IS 10500:2012 Acceptable Limits)
#define DRINKING_PH_MIN             6.50f
#define DRINKING_PH_MAX             8.50f
#define DRINKING_PH_CRIT_MIN        5.50f
#define DRINKING_PH_CRIT_MAX        9.50f
#define DRINKING_TURB_MAX_NTU       1.00f     // Strict IS 10500 acceptable limit
#define DRINKING_TURB_CRIT_NTU      5.00f
#define DRINKING_TDS_MAX_PPM        500.0f    // Strict IS 10500 acceptable limit
#define DRINKING_TDS_CRIT_PPM       1000.0f

// Profile B: REGULAR USAGE MODE (Provisional Configurable Operational Defaults)
#define REGULAR_PH_MIN              6.00f
#define REGULAR_PH_MAX              9.00f
#define REGULAR_PH_CRIT_MIN         5.00f
#define REGULAR_PH_CRIT_MAX         10.00f
#define REGULAR_TURB_MAX_NTU        10.00f
#define REGULAR_TURB_CRIT_NTU       25.00f
#define REGULAR_TDS_MAX_PPM         1000.0f
#define REGULAR_TDS_CRIT_PPM        2000.0f

// Hysteresis Margins (prevent rapid oscillation near thresholds)
#define THRESHOLD_PH_HYSTERESIS     0.15f
#define THRESHOLD_TURB_HYSTERESIS   0.15f
#define THRESHOLD_TDS_HYSTERESIS    20.0f

// Compatibility aliases for sensor driver defaults
#define THRESHOLD_PH_WARNING_MIN    DRINKING_PH_MIN
#define THRESHOLD_PH_WARNING_MAX    DRINKING_PH_MAX
#define THRESHOLD_PH_CRITICAL_MIN   DRINKING_PH_CRIT_MIN
#define THRESHOLD_PH_CRITICAL_MAX   DRINKING_PH_CRIT_MAX
#define THRESHOLD_TURB_WARNING_NTU  DRINKING_TURB_MAX_NTU
#define THRESHOLD_TURB_CRITICAL_NTU DRINKING_TURB_CRIT_NTU

// ----------------------------------------------------------------------------
// 7. SYSTEM ENUMS AND HEALTH BITMASKS
// ----------------------------------------------------------------------------
enum AlertSeverity {
    SEVERITY_NORMAL       = 0,
    SEVERITY_WARNING      = 1,
    SEVERITY_CRITICAL     = 2,
    SEVERITY_SENSOR_FAULT = 3
};

// System Health Bitmask (Uploaded in ThingSpeak Field 7)
#define HEALTH_OK                   0x0000
#define HEALTH_WIFI_DISCONNECTED    (1 << 0)  // Bit 0: Wi-Fi offline
#define HEALTH_CLOUD_ERROR          (1 << 1)  // Bit 1: ThingSpeak upload failed
#define HEALTH_PH_FAULT             (1 << 2)  // Bit 2: pH probe error/stuck/overrange
#define HEALTH_TURB_FAULT           (1 << 3)  // Bit 3: Turbidity probe error
#define HEALTH_ADC_OVER_RANGE       (1 << 4)  // Bit 4: Electrical hazard (ADC > 3.05V)
#define HEALTH_TDS_UNAVAILABLE      (1 << 5)  // Bit 5: TDS sensor absent/unavailable
#define HEALTH_CALIBRATION_PENDING  (1 << 6)  // Bit 6: One or more probes uncalibrated
#define HEALTH_DEMO_MODE_ACTIVE     (1 << 7)  // Bit 7: Demo mode simulated data
#define HEALTH_TDS_FAULT            (1 << 8)  // Bit 8: TDS probe disconnected/stuck/overrange
#define HEALTH_MODE_REGULAR         (1 << 9)  // Bit 9: 0=Drinking Mode, 1=Regular Usage Mode
