"""Unit tests for Pydantic schemas and bitmask decoding."""

import pytest
from app.schemas.sensor import SystemHealthResponse, SensorReadingCreate


def test_system_health_from_bitmask_clean():
    # Code 0 = perfectly healthy, Wi-Fi OK, Cloud OK, All sensors OK, Safe, No demo
    health = SystemHealthResponse.from_bitmask(0)
    assert health.wifi_connected is True
    assert health.cloud_synced is True
    assert health.ph_sensor_healthy is True
    assert health.turbidity_sensor_healthy is True
    assert health.electrical_safe is True
    assert health.calibration_pending is False
    assert health.overall_status == "OPERATIONAL"


def test_system_health_from_bitmask_faults():
    # Bit 0 (WiFi off) + Bit 4 (ADC over-range) + Bit 5 (TDS unavailable) + Bit 6 (Cal pending)
    code = (1 << 0) | (1 << 4) | (1 << 5) | (1 << 6)
    health = SystemHealthResponse.from_bitmask(code)
    assert health.wifi_connected is False
    assert health.electrical_safe is False
    assert health.tds_installed is False
    assert health.calibration_pending is True
    assert health.overall_status == "ELECTRICAL HAZARD"


def test_sensor_reading_create_validation():
    # Valid reading
    reading = SensorReadingCreate(
        ph=7.25,
        turbidity=1.2,
        tds=None,
        alert_severity=0,
        ph_board_voltage=2.50,
        turbidity_board_voltage=4.20,
        health_code=0,
    )
    assert reading.ph == 7.25
    assert reading.tds is None
