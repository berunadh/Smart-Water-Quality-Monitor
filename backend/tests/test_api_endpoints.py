"""Integration tests for all FastAPI REST endpoints using an isolated temporary SQLite DB."""

from datetime import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.database.session import engine
from app.models.water_reading import WaterReadingModel
from app.services.demo_service import DemoService

client = TestClient(app)


def test_tests_use_isolated_database():
    """Verify pytest runs against a temporary DB and never mutates backend/water_quality.db."""
    db_url = str(engine.url)
    assert "hydrosense_pytest_" in db_url
    assert "test_water_quality.db" in db_url


def test_api_health(isolated_app_db):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "operating_mode" in data
    assert "cloud_connectivity" in data


def test_system_status_tds_calibrated(isolated_app_db):
    """Latest reading has calibrated pH, Turbidity, and TDS -> OPERATIONAL and tds_installed=True."""
    reading = WaterReadingModel(
        device_id="esp32-water-monitor-01",
        timestamp=datetime.utcnow(),
        ph=7.25,
        turbidity=0.45,
        tds=342.0,
        ph_voltage=2.50,
        turbidity_voltage=4.20,
        tds_voltage=0.945,
        ph_calibrated=True,
        turbidity_calibrated=True,
        tds_calibrated=True,
        alert_severity=0,
        health_code=0x0000,
        sensor_health_summary="OPERATIONAL",
        alert_messages="WATER SYSTEM NORMAL",
        data_source="thingspeak",
        operating_mode="real",
        water_quality_mode="drinking",
        is_valid=True,
        is_stale=False,
    )
    isolated_app_db.add(reading)
    isolated_app_db.commit()

    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["overall_status"] == "OPERATIONAL"
    assert data["electrical_safe"] is True
    assert data["tds_installed"] is True
    assert data["tds_sensor_healthy"] is True
    assert data["calibration_pending"] is False


def test_system_status_tds_unavailable(isolated_app_db):
    """Bit 5 (HEALTH_TDS_UNAVAILABLE) must report tds_installed=False without fabricating a fault."""
    reading = WaterReadingModel(
        device_id="esp32-water-monitor-01",
        timestamp=datetime.utcnow(),
        ph=7.25,
        turbidity=0.45,
        tds=None,
        ph_voltage=2.50,
        turbidity_voltage=4.20,
        tds_voltage=None,
        ph_calibrated=True,
        turbidity_calibrated=True,
        tds_calibrated=False,
        alert_severity=0,
        health_code=(1 << 5),
        data_source="thingspeak",
        operating_mode="real",
        is_valid=True,
    )
    isolated_app_db.add(reading)
    isolated_app_db.commit()

    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["tds_installed"] is False
    assert data["tds_sensor_healthy"] is True
    assert data["electrical_safe"] is True


def test_system_status_tds_uncalibrated(isolated_app_db):
    """TDS present on GPIO35 but awaiting calibration -> tds_installed=True, calibration_pending=True."""
    reading = WaterReadingModel(
        device_id="esp32-water-monitor-01",
        timestamp=datetime.utcnow(),
        ph=7.25,
        turbidity=0.45,
        tds=None,
        ph_voltage=2.50,
        turbidity_voltage=4.20,
        tds_voltage=0.142,
        ph_calibrated=True,
        turbidity_calibrated=True,
        tds_calibrated=False,
        alert_severity=0,
        health_code=(1 << 6),  # HEALTH_CALIBRATION_PENDING
        data_source="thingspeak",
        operating_mode="real",
        is_valid=True,
    )
    isolated_app_db.add(reading)
    isolated_app_db.commit()

    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["tds_installed"] is True
    assert data["tds_sensor_healthy"] is True
    assert data["calibration_pending"] is True
    assert data["overall_status"] == "CALIBRATION PENDING"


def test_system_status_no_readings_available(isolated_app_db, monkeypatch):
    """With empty DB in real mode, /api/system/status reports AWAITING_TELEMETRY cleanly."""
    monkeypatch.setattr(settings, "DATA_MODE", "real")

    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["overall_status"] == "AWAITING_TELEMETRY"
    assert data["tds_installed"] is False
    assert data["data_freshness"] == "NO_DATA"
    assert data["calibration_pending"] is True


def test_system_status_latest_reading_sensor_fault(isolated_app_db):
    """Bit 8 (HEALTH_TDS_FAULT) reports SENSOR FAULT; Bit 4 (OVER_RANGE) reports ELECTRICAL HAZARD."""
    fault_reading = WaterReadingModel(
        device_id="esp32-water-monitor-01",
        timestamp=datetime.utcnow(),
        ph=7.25,
        turbidity=0.45,
        tds=None,
        ph_voltage=2.50,
        turbidity_voltage=4.20,
        tds_voltage=0.0,
        ph_calibrated=True,
        turbidity_calibrated=True,
        tds_calibrated=False,
        alert_severity=3,
        health_code=(1 << 8),  # HEALTH_TDS_FAULT
        data_source="thingspeak",
        operating_mode="real",
        is_valid=False,
    )
    isolated_app_db.add(fault_reading)
    isolated_app_db.commit()

    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["tds_sensor_healthy"] is False
    assert data["electrical_safe"] is True
    assert data["overall_status"] == "SENSOR FAULT"

    # Over-range fault escalates to ELECTRICAL HAZARD
    fault_reading.health_code = (1 << 4) | (1 << 8)
    fault_reading.tds_voltage = 3.12
    isolated_app_db.commit()

    res_haz = client.get("/api/system/status")
    assert res_haz.status_code == 200
    haz = res_haz.json()
    assert haz["electrical_safe"] is False
    assert haz["tds_sensor_healthy"] is False
    assert haz["overall_status"] == "ELECTRICAL HAZARD"


def test_readings_latest(isolated_app_db):
    DemoService.seed_demo_history(isolated_app_db, count=5)
    res = client.get("/api/readings/latest")
    assert res.status_code == 200
    data = res.json()
    assert data is not None
    assert "ph" in data
    assert "turbidity" in data
    assert "tds" in data
    assert "tds_voltage" in data
    assert "water_quality_mode" in data
    assert "operating_mode" in data
    assert "data_source" in data


def test_readings_history(isolated_app_db):
    DemoService.seed_demo_history(isolated_app_db, count=12)
    res = client.get("/api/readings/history?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 10


def test_readings_statistics(isolated_app_db):
    DemoService.seed_demo_history(isolated_app_db, count=5)
    res = client.get("/api/readings/statistics?hours=24")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 5
    assert "ph_mean" in data


def test_alerts_summary(isolated_app_db):
    res = client.get("/api/alerts")
    assert res.status_code == 200
    data = res.json()
    assert "total_active" in data
    assert "recent_alerts" in data


def test_ml_anomalies_endpoint(isolated_app_db):
    DemoService.seed_demo_history(isolated_app_db, count=30)
    res = client.get("/api/ml/anomalies?limit=30")
    assert res.status_code == 200
    data = res.json()
    assert "anomalies" in data
    assert "analyzed_samples" in data


def test_ml_trends_endpoint(isolated_app_db):
    DemoService.seed_demo_history(isolated_app_db, count=30)
    res = client.get("/api/ml/trends?limit=30")
    assert res.status_code == 200
    data = res.json()
    assert "ph_drift" in data
    assert "turbidity_drift" in data


def test_ml_summary_endpoint(isolated_app_db):
    DemoService.seed_demo_history(isolated_app_db, count=30)
    res = client.get("/api/ml/summary")
    assert res.status_code == 200
    data = res.json()
    assert "insights" in data
    assert "dominant_trend" in data


def test_chat_endpoint(isolated_app_db):
    DemoService.seed_demo_history(isolated_app_db, count=5)
    payload = {"message": "What is the current water status?"}
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert "source" in data
    assert "context_used" in data


def test_demo_inject_endpoint(isolated_app_db):
    res = client.post("/api/demo/inject/warning")
    assert res.status_code == 200
    data = res.json()
    assert "alert_severity" in data
    assert "tds_voltage" in data

    # Uncalibrated demo scenario must strictly preserve null calibrated metrics
    res_uncal = client.post("/api/demo/inject/uncalibrated")
    assert res_uncal.status_code == 200
    uncal_data = res_uncal.json()
    assert uncal_data["ph"] is None
    assert uncal_data["turbidity"] is None
    assert uncal_data["tds"] is None
    assert uncal_data["tds_calibrated"] is False
    assert uncal_data["alert_severity"] == 0
