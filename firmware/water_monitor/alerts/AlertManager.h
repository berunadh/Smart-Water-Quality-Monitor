#pragma once

#include <Arduino.h>
#include "../config.h"

/**
 * ============================================================================
 * ALERT & BUZZER MANAGER
 * ============================================================================
 * Pin: GPIO25 (Signal 'S' on buzzer module)
 * 
 * Safety & Acoustic Rules:
 * 1. 100% Non-blocking state machine using millis().
 * 2. Distinct patterns for Startup, Warning, Critical, and Sensor Fault.
 * 3. Cooldown timer prevents acoustic fatigue while OLED stays alarming.
 * 4. Works entirely locally - independent of Wi-Fi or Cloud status.
 * 
 * IMPORTANT DISCLAIMER:
 * Normal sensor readings do not prove water is potable. Never declare water
 * safe for human consumption based on basic pH/Turbidity sensors alone.
 * ============================================================================
 */

enum BuzzerPattern {
    PATTERN_OFF,
    PATTERN_STARTUP,
    PATTERN_WARNING,
    PATTERN_CRITICAL,
    PATTERN_FAULT
};

class AlertManager {
public:
    AlertManager(uint8_t pin = PIN_BUZZER)
        : _pin(pin),
          _pattern(PATTERN_OFF),
          _buzzerState(false),
          _lastToggleMillis(0),
          _patternStep(0),
          _alarmStartMillis(0),
          _inCooldown(false),
          _cooldownStartMillis(0) {}

    void begin() {
        pinMode(_pin, OUTPUT);
        setBuzzer(false);
        playStartupBeep();
    }

    void playStartupBeep() {
        _pattern = PATTERN_STARTUP;
        _patternStep = 0;
        _lastToggleMillis = millis();
        setBuzzer(true);
    }

    /**
     * Updates buzzer state machine cleanly without blocking.
     * 
     * STRICT RULE:
     * Buzzer ONLY activates when thresholdViolated == true (i.e., at least one
     * valid, calibrated sensor exceeds the active mode's allowed range).
     * Never activates for uncalibrated sensors, disconnected probes, or faults.
     */
    void update(uint32_t currentMillis, AlertSeverity thresholdSeverity, bool thresholdViolated) {
        // 1. Disarm immediately if no valid calibrated threshold violation exists
        if (!thresholdViolated || thresholdSeverity < SEVERITY_WARNING) {
            if (_pattern != PATTERN_STARTUP) {
                _pattern = PATTERN_OFF;
                _inCooldown = false;
                setBuzzer(false);
            } else {
                executePattern(currentMillis);
            }
            return;
        }

        // 2. Map calibrated threshold violation severity to acoustic pattern
        BuzzerPattern requestedPattern = (thresholdSeverity >= SEVERITY_CRITICAL)
                                             ? PATTERN_CRITICAL
                                             : PATTERN_WARNING;

        // Check acoustic cooldown to prevent infinite blaring
        if (_inCooldown) {
            if (currentMillis - _cooldownStartMillis >= BUZZER_COOLDOWN_MS) {
                _inCooldown = false; // Cooldown finished, resume alerting if condition persists
                _alarmStartMillis = currentMillis;
            } else {
                setBuzzer(false);
                return;
            }
        } else if (_pattern != PATTERN_OFF && _pattern != PATTERN_STARTUP) {
            if (currentMillis - _alarmStartMillis >= BUZZER_MAX_ALARM_MS) {
                _inCooldown = true;
                _cooldownStartMillis = currentMillis;
                setBuzzer(false);
                return;
            }
        }

        // If pattern changed, reset pattern step
        if (requestedPattern != _pattern && _pattern != PATTERN_STARTUP) {
            _pattern = requestedPattern;
            _patternStep = 0;
            _lastToggleMillis = currentMillis;
            _alarmStartMillis = currentMillis;
        }

        // Execute pattern state machine
        executePattern(currentMillis);
    }

private:
    uint8_t _pin;
    BuzzerPattern _pattern;
    bool _buzzerState;
    uint32_t _lastToggleMillis;
    uint8_t _patternStep;
    uint32_t _alarmStartMillis;
    bool _inCooldown;
    uint32_t _cooldownStartMillis;

    void setBuzzer(bool on) {
        _buzzerState = on;
        bool pinLevel = BUZZER_ACTIVE_LOW ? !on : on;
        digitalWrite(_pin, pinLevel ? HIGH : LOW);
    }

    void executePattern(uint32_t now) {
        switch (_pattern) {
            case PATTERN_STARTUP:
                // Single 120ms chirp
                if (now - _lastToggleMillis >= 120) {
                    setBuzzer(false);
                    _pattern = PATTERN_OFF;
                }
                break;

            case PATTERN_WARNING:
                // 150ms ON, 850ms OFF
                if (_buzzerState && (now - _lastToggleMillis >= 150)) {
                    setBuzzer(false);
                    _lastToggleMillis = now;
                } else if (!_buzzerState && (now - _lastToggleMillis >= 850)) {
                    setBuzzer(true);
                    _lastToggleMillis = now;
                }
                break;

            case PATTERN_CRITICAL:
                // Double beep: 100ms ON, 100ms OFF, 100ms ON, 600ms OFF
                if (_patternStep == 0 && (now - _lastToggleMillis >= 100)) {
                    setBuzzer(false);
                    _patternStep = 1;
                    _lastToggleMillis = now;
                } else if (_patternStep == 1 && (now - _lastToggleMillis >= 100)) {
                    setBuzzer(true);
                    _patternStep = 2;
                    _lastToggleMillis = now;
                } else if (_patternStep == 2 && (now - _lastToggleMillis >= 100)) {
                    setBuzzer(false);
                    _patternStep = 3;
                    _lastToggleMillis = now;
                } else if (_patternStep == 3 && (now - _lastToggleMillis >= 600)) {
                    setBuzzer(true);
                    _patternStep = 0;
                    _lastToggleMillis = now;
                }
                break;

            case PATTERN_FAULT:
                // 400ms ON, 1600ms OFF
                if (_buzzerState && (now - _lastToggleMillis >= 400)) {
                    setBuzzer(false);
                    _lastToggleMillis = now;
                } else if (!_buzzerState && (now - _lastToggleMillis >= 1600)) {
                    setBuzzer(true);
                    _lastToggleMillis = now;
                }
                break;

            case PATTERN_OFF:
            default:
                setBuzzer(false);
                break;
        }
    }
};
