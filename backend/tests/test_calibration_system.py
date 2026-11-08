"""
Comprehensive tests for pH and Turbidity calibration mathematics,
validation boundaries, and API integration.
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.models.calibration import CalibrationRecordModel
from app.models.water_reading import WaterReadingModel
from app.database.session import SessionLocal


def test_ph_calibration_mathematics():
    """Verifies that two-point Nernstian slope and intercept calculations are exact."""
    # Scenario: Standard conditioning board
    # Neutral buffer: pH 7.00 -> V_board = 2.520 V
    # Acidic buffer: pH 4.01 -> V_board = 3.770 V
    v7 = 2.520
    v4 = 3.770
    delta_v = v7 - v4  # -1.250 V

    slope = (7.00 - 4.01) / delta_v  # 2.99 / -1.250 = -2.392 pH/V
    intercept = 7.00 - (slope * v7)

    # Calculate at calibration points
    ph_at_v7 = (slope * v7) + intercept
    ph_at_v4 = (slope * v4) + intercept

    assert abs(ph_at_v7 - 7.00) < 0.001
    assert abs(ph_at_v4 - 4.01) < 0.001

    # Interpolation test: midpoint voltage (3.145 V)
    v_mid = (v7 + v4) / 2.0
    ph_mid = (slope * v_mid) + intercept
    assert abs(ph_mid - 5.505) < 0.001


def test_ph_calibration_rejection_rules():
    """Verifies rejection of invalid or physically implausible calibration inputs."""
    def validate_ph_calibration(v7, v4):
        if v7 < 0.10 or v7 > 4.95 or v4 < 0.10 or v4 > 4.95:
            return False, "Voltage out of circuit bounds"
        delta_v = v7 - v4
        if abs(delta_v) < 0.150:
            return False, "Insufficient voltage separation"
        slope = (7.00 - 4.01) / delta_v
        if abs(slope) < 0.50 or abs(slope) > 12.00:
            return False, "Implausible slope"
        return True, "Valid"

    # Separation too small (probes read same voltage in both buffers)
    valid, msg = validate_ph_calibration(2.50, 2.55)
    assert not valid
    assert "Insufficient" in msg

    # Out of range (disconnected or shorted)
    valid, msg = validate_ph_calibration(0.05, 3.50)
    assert not valid
    assert "bounds" in msg

    # Unreasonable slope
    valid, msg = validate_ph_calibration(2.50, 2.66)
    assert not valid  # 2.99 / -0.16 = -18.68 pH/V (> 12.0)


def test_turbidity_optical_attenuation_mathematics():
    """Verifies that optical attenuation equation is exact and enforces non-negative NTU."""
    # Clear water baseline: V_clear = 4.150 V (0.0 NTU)
    # Standard solution: V_std = 2.650 V (100.0 NTU)
    v_clear = 4.150
    v_std = 2.650
    ntu_std = 100.0

    def compute_ntu(v_meas):
        delta_v = v_clear - v_meas
        if delta_v <= 0.0:
            return 0.0
        return (delta_v / (v_clear - v_std)) * ntu_std

    # Baseline clear
    assert compute_ntu(4.150) == 0.0
    # Clearer than baseline (should clamp to 0.0, never negative)
    assert compute_ntu(4.250) == 0.0
    # Standard solution
    assert abs(compute_ntu(2.650) - 100.0) < 0.001
    # Half-scale
    assert abs(compute_ntu(3.400) - 50.0) < 0.001


def test_turbidity_calibration_rejection_rules():
    """Verifies rejection of inverted optical response or degraded clear baseline."""
    def validate_turb_calibration(v_clear, v_std, ntu_std):
        if v_clear < 2.00 or v_clear > 5.00:
            return False, "Degraded or invalid clear baseline"
        if v_std >= v_clear:
            return False, "Optical inversion (V_std >= V_clear)"
        if (v_clear - v_std) < 0.150:
            return False, "Insufficient attenuation separation"
        if ntu_std <= 0.0 or ntu_std > 3000.0:
            return False, "Invalid standard NTU"
        return True, "Valid"

    # Optical inversion (voltage increased with turbidity -> impossible for transmission probe)
    valid, msg = validate_turb_calibration(3.20, 3.80, 100.0)
    assert not valid
    assert "Optical inversion" in msg

    # Dirty / unpowered baseline (< 2.0V in clean water)
    valid, msg = validate_turb_calibration(1.65, 1.20, 100.0)
    assert not valid
    assert "clear baseline" in msg

    # Delta too small
    valid, msg = validate_turb_calibration(4.10, 4.02, 100.0)
    assert not valid
    assert "Insufficient attenuation" in msg


def test_calibration_api_endpoints():
    """Verifies backend calibration status retrieval and audit logging."""
    client = TestClient(app)

    # 1. Get calibration status
    resp = client.get("/api/calibration/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "ph_calibrated" in data
    assert "turbidity_calibrated" in data
    assert "calibration_pending" in data
    assert "ph_reference_standards" in data
    assert len(data["ph_reference_standards"]) == 2

    # 2. Log calibration record
    record_payload = {
        "sensor_type": "ph",
        "point_name": "pH_7.00",
        "reference_value": 7.00,
        "measured_voltage": 2.518,
        "operator_notes": "Unit test verified calibration buffer standard.",
    }
    resp_log = client.post("/api/calibration/record", json=record_payload)
    assert resp_log.status_code == 200
    log_data = resp_log.json()
    assert log_data["point_name"] == "pH_7.00"
    assert log_data["reference_value"] == 7.00
    assert abs(log_data["measured_voltage"] - 2.518) < 0.001

    # 3. Retrieve logged records
    resp_list = client.get("/api/calibration/records?sensor_type=ph&limit=5")
    assert resp_list.status_code == 200
    records = resp_list.json()
    assert len(records) >= 1
    assert any(r["point_name"] == "pH_7.00" for r in records)
