"""Calibration-provenance contract tests for API responses."""

from app.schemas.sensor import SensorReadingResponse


def reading(**overrides):
    values = dict(
        id=1,
        timestamp="2026-11-11T00:00:00",
        ph=None,
        turbidity=None,
        tds=None,
        ph_voltage=2.5,
        turbidity_voltage=2.5,
        health_code=(1 << 6),
    )
    values.update(overrides)
    return SensorReadingResponse(**values)


def test_confidence_never_upgrades_provisional_or_missing_calibration():
    uncalibrated = reading()
    provisional = reading(ph=7.1, health_code=(1 << 12) | (1 << 6))

    assert uncalibrated.ph_calibration_status == "UNCALIBRATED"
    assert provisional.ph_calibration_status == "MODEL_BASED_PROVISIONAL"
    assert provisional.turbidity_calibration_status == "UNCALIBRATED"


def test_confidence_distinguishes_verified_demo_and_fault():
    verified = reading(ph=7.1, ph_calibrated=True, health_code=0)
    demo = reading(ph=7.1, ph_calibrated=True, operating_mode="demo", health_code=(1 << 7))
    fault = reading(ph=7.1, ph_calibrated=True, health_code=(1 << 2))

    assert verified.ph_calibration_status == "VERIFIED_CALIBRATION"
    assert demo.ph_calibration_status == "DEMONSTRATION_ESTIMATE"
    assert fault.ph_calibration_status == "SENSOR_FAULT"
