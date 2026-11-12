#pragma once

#include <math.h>

// Presentation-only pH estimator for the known RO and tap-water demo
// profiles. It deliberately accepts already-calculated TDS and turbidity,
// never ADC readings or the physical pH signal.
struct PhDemoDisplayConfig {
    float roTdsPpm;
    float tapTdsPpm;
    float roTurbidity;
    float tapTurbidity;
    float roPh;
    float tapPh;
    float minPh;
    float maxPh;
    float maximumContaminatedRise;
    float contaminatedAdjustment;
    float filterAlpha;
};

inline float clampPhDemoValue(float value, float low, float high) {
    return value < low ? low : (value > high ? high : value);
}

inline float phDemoProfileTarget(float tdsPpm, float turbidity,
                                 const PhDemoDisplayConfig& config) {
    if (!isfinite(tdsPpm) || !isfinite(turbidity)) return NAN;

    const float tdsSpan = config.tapTdsPpm - config.roTdsPpm;
    const float turbiditySpan = config.tapTurbidity - config.roTurbidity;
    if (tdsSpan <= 0.0f || turbiditySpan <= 0.0f || config.minPh > config.maxPh) return NAN;

    const float referenceBlend = 0.5f * (
        clampPhDemoValue((tdsPpm - config.roTdsPpm) / tdsSpan, 0.0f, 1.0f) +
        clampPhDemoValue((turbidity - config.roTurbidity) / turbiditySpan, 0.0f, 1.0f));
    const float referencePh = config.roPh + (config.tapPh - config.roPh) * referenceBlend;

    const float contaminationBlend = 0.5f * (
        clampPhDemoValue((tdsPpm - config.tapTdsPpm) / tdsSpan, 0.0f, 1.0f) +
        clampPhDemoValue((turbidity - config.tapTurbidity) / turbiditySpan, 0.0f, 1.0f));

    return clampPhDemoValue(referencePh +
                                config.maximumContaminatedRise * contaminationBlend +
                                config.contaminatedAdjustment,
                            config.minPh, config.maxPh);
}

class PhDemoDisplayEstimator {
public:
    void reset() { _filtered = NAN; }

    float update(float tdsPpm, float turbidity, const PhDemoDisplayConfig& config) {
        const float target = phDemoProfileTarget(tdsPpm, turbidity, config);
        if (!isfinite(target)) return NAN;

        const float alpha = clampPhDemoValue(config.filterAlpha, 0.0f, 1.0f);
        _filtered = isfinite(_filtered) ? _filtered + alpha * (target - _filtered) : target;
        return _filtered;
    }

private:
    float _filtered = NAN;
};
