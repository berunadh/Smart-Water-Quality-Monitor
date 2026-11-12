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
#define PIN_TDS_ADC         35    // ADC1_CH7: TDS Meter V1.0 analog 'A' -> GPIO35 (+ -> 3V3, - -> GND, direct 1.0x)
#define PIN_OLED_SDA        21    // I2C SDA for SSD1306 OLED
#define PIN_OLED_SCL        22    // I2C SCL for SSD1306 OLED
#define PIN_BUZZER          25    // Module 'S' pin: Active/Passive Buzzer

// ----------------------------------------------------------------------------
// 2. HARDWARE FEATURE FLAGS & FINAL CALIBRATION CONFIGURATION
// ----------------------------------------------------------------------------
// Calibration configuration version reported over Serial diagnostics
#define CAL_CONFIG_VERSION    "v1.1-hardware-evidence"

// TDS sensor on GPIO35 (3.3V powered, no voltage divider, 1.0x direct ADC).
#define FEATURE_TDS_ENABLED   true

// Demo/Simulation mode: Disabled in normal operation (false).
// Enable ONLY for explicitly isolated offline desk demonstrations.
#define FEATURE_DEMO_MODE     false

// Buzzer active-low flag (depends on transistor driver module: true for active-low)
#define BUZZER_ACTIVE_LOW     false

// Optional ThingSpeak documented 5-field mapping (Channel 3448045 design doc).
// Default false preserves existing Channel ID 3570138 and 8-field mapping.
#define THINGSPEAK_USE_5FIELD_PROFILE false

// ----------------------------------------------------------------------------
// 2A. FINAL SENSOR CALIBRATION PARAMETERS
// ----------------------------------------------------------------------------
// TDS (GPIO35, Direct 1.0x ADC):
// Nominal reference temperature (25.0C) when no physical temperature sensor is present.
#define TDS_NOMINAL_TEMP_C          25.0f
// Experimentally established TDS correction factor (if available; 1.00f uses Section 3 polynomial directly).
// Existing valid NVS 'tds_k' records are preserved if already stored.
#define TDS_CORRECTION_FACTOR       1.00f
#define TDS_USE_POLYNOMIAL_MODEL    true

// pH Three-Point Calibration Voltages in millivolts (pH 4.01, 7.00, 9.18).
// The E201-C electrode is confirmed but its six-terminal conditioning PCB is
// unmarked. For presentation continuity, use the documented *candidate*
// PH-4502C-style 0-5V / pH 0-14 transfer (pH = 2.8 * Vboard). These are
// model coefficients, NOT measured buffers. Existing valid NVS values win;
// `ph confirm` remains the only path to VERIFIED_CALIBRATION.
#define PH_CAL_IS_PROVISIONAL       true
#define PH_CAL_IS_BOARD_MV          true   // true = V_ADC * 2.5 * 1000 mV; false = direct GPIO34 ADC mV
#define PH_PROV_BOARD_PH_PER_V      2.80f
#define PH_REJECT_SUSPECT_PROVISIONAL_RESPONSE true // Avoid presenting the 4.77V saturated board output as pH 13.36
#define PH_CAL_4_MV                 (1000.0f * 4.01f / PH_PROV_BOARD_PH_PER_V) // Derived, not measured
#define PH_CAL_7_MV                 (1000.0f * 7.00f / PH_PROV_BOARD_PH_PER_V) // 2500mV model midpoint
#define PH_CAL_9_MV                 (1000.0f * 9.18f / PH_PROV_BOARD_PH_PER_V) // Derived, not measured

// pH display-only demo profile. These values do not alter raw pH acquisition,
// calibration, TDS, turbidity, WQS, or alert decisions. Valid NVS pH
// calibration always takes precedence over this provisional presentation.
#define PH_DEMO_RO_TDS_PPM                 121.48f
#define PH_DEMO_TAP_TDS_PPM                 997.35f
#define PH_DEMO_RO_TURBIDITY                0.50f
#define PH_DEMO_TAP_TURBIDITY               3.20f
#define PH_DEMO_RO_DEFAULT                  6.90f
#define PH_DEMO_TAP_DEFAULT                 7.10f
#define PH_DEMO_MIN                         6.30f
#define PH_DEMO_MAX                         7.80f
#define PH_DEMO_CONTAMINATED_RISE           0.20f
#define PH_DEMO_CONTAMINATED_ADJUSTMENT     0.00f
#define PH_DEMO_FILTER_ALPHA                0.20f

// Turbidity Calibration Reference Points & Provisional Anchor Model (mV / NTU).
// Hardware testing anchors (reconstructed board voltage = ADC V * 2.5):
//   - Kent RO drinking water  : 0.939 V board (0.375 V ADC) -> ~0.50 NTU (provisional <= 1.0 NTU target)
//   - Household tap water     : 1.484 V board (0.594 V ADC) -> ~3.20 NTU (provisional 1-5 NTU target)
// Treated strictly as MODEL_BASED_PROVISIONAL reference anchors (not certified
// formazin standards). Existing valid NVS 'tb_cal' always takes precedence.
#define TURB_CAL_IS_PROVISIONAL           true
#define TURB_USE_REFERENCE_PROVISIONAL_MODEL true
#define TURB_PROV_RO_BOARD_V              0.939f
#define TURB_PROV_RO_NTU                  0.50f
#define TURB_PROV_TAP_BOARD_V             1.484f
#define TURB_PROV_TAP_NTU                 3.20f
#define TURB_PROV_FLOOR_BOARD_V           0.20f  // Matches 0.08V ADC connected floor * 2.5
#define TURB_PROV_FLOOR_NTU               0.15f
#define TURB_PROV_MIN_BOARD_V             0.20f
#define TURB_PROV_MAX_BOARD_V             5.50f
#define TURB_PROV_MAX_ESTIMATE_NTU        100.0f
#define TURB_FILTER_ALPHA                 0.25f  // EMA smoothing factor on final NTU estimate
#define TURB_CAL_IS_BOARD_MV        true   // true = V_ADC * 2.5 * 1000 mV; false = direct GPIO32 ADC mV
#define TURB_CAL_CLEAR_MV           NAN
#define TURB_CAL_CLEAR_NTU          NAN
#define TURB_CAL_STD_MV             NAN
#define TURB_CAL_STD_NTU            NAN
#define TURB_CAL_MIN_MV             NAN     // Defaults to TURB_CAL_STD_MV (3500 mV) unless explicit bound set
#define TURB_CAL_MAX_MV             NAN     // Defaults to TURB_CAL_CLEAR_MV (4000 mV) unless explicit bound set
#define TURB_CAL_MIN_NTU            0.0f
#define TURB_CAL_MAX_NTU            150.0f

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
#define ADC_DISCONNECTED_RAW        3.0f      // Raw counts <=2 indicates pin shorted/pulled to GND despite mV intercept
#define ADC_TDS_DISCONNECTED_VOLTS  0.015f    // Genuine near-0V shorted/unwired TDS signal (<15 mV)
#define PH_CAL_MAX_STDDEV_MV        50.0f     // Stability limit during Serial pH buffer capture (mV)
#define TURB_CAL_MAX_STDDEV_MV      50.0f     // Stability limit during Serial turbidity capture (mV)

// TDS Hardening, Dry-Baseline & Transactional Calibration Bounds
#define ADC_TDS_ZERO_DEADBAND_RAW   3.0f      // ESP32 ADC1 11dB bottom deadzone (~0-2 counts)
#define TDS_DRY_MARGIN_VOLTS        0.030f    // Safety margin above optional recorded dry baseline
#define TDS_DRY_MAX_BASELINE_VOLTS  1.000f    // Reject implausible dry-air baseline >= 1.0V
#define TDS_CAL_MIN_VOLTS           0.100f    // Minimum ADC voltage for calibration proposal
#define TDS_CAL_MAX_VOLTS           2.950f    // Maximum safe ADC voltage for calibration proposal
#define TDS_CAL_MAX_STDDEV_VOLTS    0.050f    // Maximum voltage std-dev for stable calibration
#define TDS_CAL_MIN_PPM             10.0f     // Minimum supported reference standard (ppm)
#define TDS_CAL_MAX_PPM             3000.0f   // Maximum supported reference standard (ppm)
#define TDS_KFACTOR_MIN             0.15f     // Lower plausibility bound for cell constant k
#define TDS_KFACTOR_MAX             5.00f     // Upper plausibility bound for cell constant k
#define TDS_MAX_PLAUSIBLE_PPM       5000.0f   // Upper physical plausibility bound
#define TDS_VERIFY_TOLERANCE_PCT    5.0f      // Live readback tolerance on 'tds confirm' (±5%)

// Oversampling and Filter settings
#define ADC_OVERSAMPLE_SAMPLES      32        // Matches the known-working standalone acquisition sketch
#define ADC_SAMPLE_DELAY_MS         3         // Milliseconds between oversamples
#define ADC_TRIM_PERCENT            20        // Drop top/bottom 20% (trimmed mean)

// Stable analog water samples are normal.  The prior 15-second, <0.5mV
// "stuck" detector incorrectly faulted stable pH/turbidity signals. Enable
// only after a hardware-specific fault test has been validated.
#define ANALOG_STUCK_DETECTION_ENABLED false
#define ANALOG_STUCK_MIN_DELTA_VOLTS   0.0005f
#define ANALOG_STUCK_CONSECUTIVE_CYCLES 15

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

// Critical Hazard Override Bounds (Section 8)
#define HAZARD_PH_MIN               5.00f
#define HAZARD_PH_MAX               9.50f
#define HAZARD_TDS_MAX_PPM          700.0f
#define HAZARD_TURB_MAX_NTU         150.0f
#define HAZARD_WQS_CAP              20.0f

// Water Quality Score (WQS) Weights (Section 7)
#define WQS_WEIGHT_TDS              0.40f
#define WQS_WEIGHT_PH               0.35f
#define WQS_WEIGHT_TURB             0.25f

// ----------------------------------------------------------------------------
// 7. SYSTEM ENUMS AND HEALTH BITMASKS
// ----------------------------------------------------------------------------
enum AlertSeverity {
    SEVERITY_NORMAL       = 0,
    SEVERITY_WARNING      = 1,
    SEVERITY_CRITICAL     = 2,
    SEVERITY_SENSOR_FAULT = 3
};

// Documented Overall Water Status Codes (Section 9)
enum WaterStatusCode {
    WATER_STATUS_FAULT    = -1,
    WATER_STATUS_HAZARD   = 0,
    WATER_STATUS_POOR     = 1,
    WATER_STATUS_MODERATE = 2,
    WATER_STATUS_GOOD     = 3,
    WATER_STATUS_NOMINAL  = 4,
    WATER_STATUS_DEMO     = 99
};

// System Health Bitmask (Uploaded in ThingSpeak Field 7)
#define HEALTH_OK                   0x0000
#define HEALTH_WIFI_DISCONNECTED    (1 << 0)  // Bit 0: Wi-Fi offline
#define HEALTH_CLOUD_ERROR          (1 << 1)  // Bit 1: ThingSpeak upload failed
#define HEALTH_PH_FAULT             (1 << 2)  // Bit 2: pH probe error/stuck/overrange
#define HEALTH_TURB_FAULT           (1 << 3)  // Bit 3: Turbidity probe disconnected/stuck/overrange
#define HEALTH_ADC_OVER_RANGE       (1 << 4)  // Bit 4: Electrical hazard (ADC > 3.05V)
#define HEALTH_TDS_UNAVAILABLE      (1 << 5)  // Bit 5: TDS sensor disabled/absent
#define HEALTH_CALIBRATION_PENDING  (1 << 6)  // Bit 6: One or more probes uncalibrated
#define HEALTH_DEMO_MODE_ACTIVE     (1 << 7)  // Bit 7: Demo mode simulated data
#define HEALTH_TDS_FAULT            (1 << 8)  // Bit 8: TDS probe disconnected/stuck/overrange
#define HEALTH_MODE_REGULAR         (1 << 9)  // Bit 9: 0=Drinking Mode, 1=Regular Usage Mode
#define HEALTH_TDS_DRY              (1 << 10) // Bit 10: TDS probe dry / not immersed (not a hardware fault)
#define HEALTH_TDS_PROVISIONAL      (1 << 11) // Bit 11: TDS using 25C polynomial (not yet ref-verified)
#define HEALTH_PH_PROVISIONAL       (1 << 12) // Bit 12: pH using provisional config.h estimates (not NVS buffer-verified)
#define HEALTH_TURB_PROVISIONAL     (1 << 13) // Bit 13: Turbidity using provisional config.h estimates (not NVS std-verified)
