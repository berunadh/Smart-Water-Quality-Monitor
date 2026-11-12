"""Comprehensive tests for TDS integration, Dual Water Quality Modes, Smart Alerts, ML, and Migrations."""

from datetime import datetime, timedelta
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database.base import Base
from app.database.migrations import run_safe_migrations
from app.models.water_reading import WaterReadingModel
from app.models.water_quality_config import WaterQualityConfigModel
from app.services.mode_service import ModeService
from app.services.validation_service import ValidationService
from app.services.alert_service import AlertService
from app.services.thingspeak_service import ThingSpeakService
from app.schemas.thingspeak import ThingSpeakFeedItem
from app.ml.anomaly_detector import RobustStatisticalDetector
from app.ml.fault_detector import SensorFaultDetector
from app.ml.trend_analyzer import TrendAnalyzer
from app.chatbot.tools import WaterChatbotTools


@pytest.fixture
def isolated_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_tds_polynomial_and_direct_adc_safety():
    """Verifies TDS 1.0x direct voltage handling (no 2.5x divider) and kFactor derivation."""
    def compute_raw_poly(v_adc):
        return (133.42 * (v_adc ** 3) - 255.86 * (v_adc ** 2) + 857.39 * v_adc) * 0.5

    # Example standalone reading: 1.876 V direct ADC
    raw_est = compute_raw_poly(1.876)
    assert raw_est > 700.0

    # Calibration with 342 ppm standard at 1.25 V
    raw_at_std = compute_raw_poly(1.250)
    k = 342.0 / raw_at_std
    assert 0.15 <= k <= 5.00
    assert abs((compute_raw_poly(1.250) * k) - 342.0) < 0.01

    # ValidationService MUST treat TDS voltage directly (no 0.40 divider ratio):
    # 1.876 V is safe (< 3.05 V)
    ok, _, _ = ValidationService.validate_reading(
        ph=7.2, turbidity=0.5, tds=None, ph_board_v=4.74, turbidity_board_v=1.46, health_code=0, tds_voltage=1.876
    )
    assert ok is True

    # 3.10 V direct on GPIO35 MUST trigger electrical hazard even though 3.10 * 0.40 would be 1.24V!
    hazard, _, notes = ValidationService.validate_reading(
        ph=7.2, turbidity=0.5, tds=None, ph_board_v=4.74, turbidity_board_v=1.46, health_code=0, tds_voltage=3.10
    )
    assert hazard is False
    assert "TDS ADC voltage" in notes


def test_drinking_mode_bis_is10500_limits(isolated_db):
    """Verifies strict BIS IS 10500:2012 limits (Turbidity <= 1.0 NTU, pH 6.5-8.5, TDS <= 500)."""
    config = ModeService.get_or_create_config(isolated_db)
    assert config.active_mode == "drinking"
    assert config.drinking_ph_min == 6.5
    assert config.drinking_ph_max == 8.5
    assert config.drinking_turbidity_max == 1.0
    assert config.drinking_tds_max == 500.0

    # Acceptable reading
    good = WaterReadingModel(
        ph=7.25, turbidity=0.55, tds=220.0,
        ph_voltage=2.5, turbidity_voltage=4.2, tds_voltage=1.1,
        ph_calibrated=True, turbidity_calibrated=True, tds_calibrated=True,
        health_code=0, is_valid=True,
    )
    ev = ModeService.evaluate_reading(good, config)
    assert ev.overall_status == "NORMAL"
    assert ev.alert_severity == 0
    assert ev.parameter_evaluations["turbidity"].status == "acceptable"

    # Warning zone (near limit: 0.90 NTU <= 1.0 NTU)
    near_limit = WaterReadingModel(
        ph=7.25, turbidity=0.92, tds=470.0,
        ph_voltage=2.5, turbidity_voltage=4.0, tds_voltage=1.4,
        ph_calibrated=True, turbidity_calibrated=True, tds_calibrated=True,
        health_code=0, is_valid=True,
    )
    ev_warn = ModeService.evaluate_reading(near_limit, config)
    assert ev_warn.overall_status == "WARNING"
    assert ev_warn.parameter_evaluations["turbidity"].status == "warning"
    assert ev_warn.parameter_evaluations["tds"].status == "warning"
    assert ev_warn.violated_parameters == []

    # Turbidity 1.5 NTU (below relaxed 5 NTU permissible limit, MUST trigger exceedance in Drinking Mode!)
    exceed_turb = WaterReadingModel(
        ph=7.25, turbidity=1.50, tds=220.0,
        ph_voltage=2.5, turbidity_voltage=3.9, tds_voltage=1.1,
        ph_calibrated=True, turbidity_calibrated=True, tds_calibrated=True,
        health_code=0, is_valid=True,
    )
    ev_breach = ModeService.evaluate_reading(exceed_turb, config)
    assert ev_breach.overall_status == "EXCEEDED"
    assert ev_breach.alert_severity >= 1
    assert any("Turbidity" in v for v in ev_breach.violated_parameters)


def test_mode_switching_and_multi_parameter_alerts(isolated_db):
    """Switching Drinking <-> Regular Usage must immediately recalculate status without mutating other profile."""
    config = ModeService.get_or_create_config(isolated_db)
    reading = WaterReadingModel(
        ph=7.40, turbidity=2.85, tds=620.0,
        ph_voltage=2.55, turbidity_voltage=3.60, tds_voltage=1.52,
        ph_calibrated=True, turbidity_calibrated=True, tds_calibrated=True,
        health_code=0, is_valid=True,
    )
    isolated_db.add(reading)
    isolated_db.commit()

    # Drinking Mode flags BOTH Turbidity (2.85 > 1.0) and TDS (620 > 500)
    ev_drink = ModeService.evaluate_reading(reading, config)
    assert ev_drink.alert_severity >= 1
    assert len(ev_drink.violated_parameters) == 2

    alert = AlertService.evaluate_and_record_alerts(isolated_db, reading)
    assert alert is not None
    assert "TURBIDITY" in alert.title and "TDS" in alert.title

    # Switch to Regular Usage Mode (defaults: 6.0-9.0 pH, 10.0 NTU, 1000 mg/L) -> immediately NORMAL!
    ModeService.switch_mode(isolated_db, "regular_usage")
    config_reg = ModeService.get_or_create_config(isolated_db)
    assert config_reg.active_mode == "regular_usage"
    ev_reg = ModeService.evaluate_reading(reading, config_reg)
    assert ev_reg.overall_status == "NORMAL"
    assert ev_reg.alert_severity == 0
    assert ev_reg.violated_parameters == []

    # Drinking profile limits remained untouched
    assert config_reg.drinking_turbidity_max == 1.0
    assert config_reg.drinking_tds_max == 500.0


def test_uncalibrated_sensors_never_normal_or_alerted(isolated_db):
    """Uncalibrated sensors remain null, classified as CALIBRATION_PENDING, and never trigger threshold alerts."""
    config = ModeService.get_or_create_config(isolated_db)
    uncal = WaterReadingModel(
        ph=None, turbidity=None, tds=None,
        ph_voltage=4.742, turbidity_voltage=1.465, tds_voltage=1.876,
        ph_calibrated=False, turbidity_calibrated=False, tds_calibrated=False,
        health_code=0x0040, is_valid=True,
    )
    ev = ModeService.evaluate_reading(uncal, config)
    assert ev.overall_status == "CALIBRATION_PENDING"
    assert ev.alert_severity == 0
    assert ev.violated_parameters == []
    assert ev.parameter_evaluations["tds"].status == "uncalibrated"

    # AlertService must NOT create a threshold alert for uncalibrated sensors
    alert = AlertService.evaluate_and_record_alerts(isolated_db, uncal)
    assert alert is None


def test_thingspeak_calibrated_tds_ingestion(isolated_db):
    """Verifies Field 3 parses calibrated TDS and optional Field 8 preserves raw TDS voltage while empty Field 3 stays None."""
    now = datetime.utcnow()
    items = [
        ThingSpeakFeedItem(
            entry_id=501,
            created_at=now,
            field1="7.20",
            field2="0.6",
            field3="345",
            field4="0",
            field5="2.52",
            field6="4.20",
            field7="0",
            field8="1.245",
        ),
        ThingSpeakFeedItem(
            entry_id=502,
            created_at=now + timedelta(seconds=20),
            field1="7.20",
            field2="0.6",
            field3="",  # Uncalibrated TDS -> MUST stay None
            field4="0",
            field5="2.52",
            field6="4.20",
            field7="64",
            field8="1.876",
        ),
        ThingSpeakFeedItem(
            entry_id=503,
            created_at=now + timedelta(seconds=40),
            field1="7.20",
            field2="0.6",
            field3="",
            field4="3",
            field5="2.52",
            field6="4.20",
            field7="272",
            field8="3.120",  # Direct GPIO35 over-range (>= 3.05V)
        ),
    ]
    res = ThingSpeakService.process_and_save_feeds(isolated_db, items)
    assert res.new_records_saved == 3
    assert res.validation_failures == 1

    r1 = isolated_db.query(WaterReadingModel).filter_by(entry_id=501).one()
    assert r1.tds == 345.0
    assert r1.tds_calibrated is True
    assert r1.tds_voltage == 1.245
    assert r1.is_valid is True

    r2 = isolated_db.query(WaterReadingModel).filter_by(entry_id=502).one()
    assert r2.tds is None
    assert r2.tds_calibrated is False
    assert r2.tds_voltage == 1.876
    assert r2.is_valid is True

    r3 = isolated_db.query(WaterReadingModel).filter_by(entry_id=503).one()
    assert r3.is_valid is False
    assert "3.05V" in (r3.validation_notes or "")


def test_ml_handles_tds_and_missing_values():
    """ML anomaly detector, fault detector, and trend analyzer must handle calibrated TDS and NaNs properly."""
    now = datetime.utcnow()
    # 1. Statistical anomaly in TDS
    df = pd.DataFrame({
        "timestamp": [now + timedelta(minutes=i) for i in range(15)],
        "ph": [7.3] * 15,
        "turbidity": [0.5] * 15,
        "tds": [210.0, 212.0, 209.0, 211.0, 215.0, 210.0, 208.0, 211.0, 213.0, 212.0, 210.0, 209.0, 211.0, 212.0, 890.0],
        "tds_voltage": [1.05] * 14 + [2.25],
    })
    anomalies = RobustStatisticalDetector(z_threshold=3.0).predict(df)
    assert any(a.parameter == "tds" and a.measured_value == 890.0 for a in anomalies)

    # 2. Direct TDS voltage over-range (>= 3.05V) in SensorFaultDetector
    df_fault = pd.DataFrame({
        "timestamp": [now],
        "ph_voltage": [4.50],
        "turbidity_voltage": [3.50],
        "tds_voltage": [3.10],
    })
    faults = SensorFaultDetector.analyze_faults(df_fault)
    assert any(f.parameter == "tds_voltage" and f.anomaly_type == "ELECTRICAL_OVER_RANGE" for f in faults)

    # 3. Missing TDS (all None) returns INSUFFICIENT_DATA, never 0 trend
    df_null_tds = pd.DataFrame({
        "timestamp": [now + timedelta(minutes=i) for i in range(10)],
        "ph": [7.3] * 10,
        "turbidity": [0.5] * 10,
        "tds": [None] * 10,
    })
    trends = TrendAnalyzer.evaluate_water_trends(df_null_tds)
    assert trends.tds_drift is not None
    assert trends.tds_drift.trend_direction == "INSUFFICIENT_DATA"


def test_non_destructive_sqlite_migration():
    """Verifies legacy water_readings tables migrate cleanly without deleting historical data."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE water_readings (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER,
                device_id VARCHAR(64) NOT NULL,
                timestamp DATETIME NOT NULL,
                ph FLOAT,
                turbidity FLOAT,
                tds FLOAT,
                ph_voltage FLOAT NOT NULL,
                turbidity_voltage FLOAT NOT NULL,
                ph_calibrated BOOLEAN NOT NULL DEFAULT 0,
                turbidity_calibrated BOOLEAN NOT NULL DEFAULT 0,
                tds_calibrated BOOLEAN NOT NULL DEFAULT 0,
                alert_severity INTEGER NOT NULL DEFAULT 0,
                health_code INTEGER NOT NULL DEFAULT 0,
                sensor_health_summary VARCHAR(64) NOT NULL DEFAULT 'OPERATIONAL',
                alert_messages VARCHAR(255) NOT NULL DEFAULT 'NORMAL',
                data_source VARCHAR(32) NOT NULL DEFAULT 'thingspeak',
                operating_mode VARCHAR(16) NOT NULL DEFAULT 'real',
                is_valid BOOLEAN NOT NULL DEFAULT 1,
                is_stale BOOLEAN NOT NULL DEFAULT 0,
                validation_notes VARCHAR(255)
            )
        """))
        conn.execute(text("""
            INSERT INTO water_readings (id, device_id, timestamp, ph, turbidity, tds, ph_voltage, turbidity_voltage)
            VALUES (1, 'esp32-water-monitor-01', '2026-11-08 12:00:00', 7.30, 0.70, NULL, 2.50, 4.10)
        """))

    run_safe_migrations(engine)

    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(water_readings)")).fetchall()}
        assert "tds_voltage" in cols
        assert "water_quality_mode" in cols
        row = conn.execute(text("SELECT ph, tds, water_quality_mode FROM water_readings WHERE id=1")).fetchone()
        assert row[0] == 7.30
        assert row[1] is None
        assert row[2] == "drinking"


def test_settings_api_endpoints_and_chatbot_context():
    """Tests mode switching & threshold update REST endpoints end-to-end."""
    client = TestClient(app)

    # Save current settings to restore at end
    initial = client.get("/api/settings/mode")
    assert initial.status_code == 200
    orig_mode = initial.json()["active_mode"]

    # Switch to regular_usage
    res_reg = client.put("/api/settings/mode", json={"mode": "regular_usage"})
    assert res_reg.status_code == 200
    assert res_reg.json()["active_mode"] == "regular_usage"
    assert res_reg.json()["active_profile"]["turbidity_max"] >= 1.0

    # Update regular usage threshold
    res_upd = client.put("/api/settings/thresholds", json={
        "mode": "regular_usage",
        "ph_min": 5.8,
        "ph_max": 9.2,
        "turbidity_max": 12.0,
        "tds_max": 1200.0,
    })
    assert res_upd.status_code == 200
    assert res_upd.json()["regular_usage_profile"]["turbidity_max"] == 12.0

    # Reset regular_usage defaults and switch back to drinking
    client.post("/api/settings/mode/reset/regular_usage")
    client.put("/api/settings/mode", json={"mode": "drinking"})
    res_drink = client.get("/api/settings/mode")
    assert res_drink.status_code == 200
    assert res_drink.json()["active_mode"] == "drinking"
    assert res_drink.json()["drinking_profile"]["turbidity_max"] == 1.0

    # Chatbot receives active mode & thresholds
    chat_res = client.post("/api/chat", json={"message": "What mode and thresholds are active?"})
    assert chat_res.status_code == 200
    assert "water_quality_mode" in chat_res.json()["context_used"]

    # Restore original mode
    client.put("/api/settings/mode", json={"mode": orig_mode})


@pytest.mark.asyncio
async def test_dry_tds_fault_and_chatbot_missing_tds_handling(isolated_db, monkeypatch):
    """Dry/faulty TDS preserves Field 3 null + Field 8 voltage, and chatbot distinguishes missing TDS."""
    from app.chatbot.agent import WaterChatbotAgent

    now = datetime.utcnow()
    dry_fault_item = ThingSpeakFeedItem(
        entry_id=701,
        created_at=now,
        field1="7.22",
        field2="0.6",
        field3="",       # Omitted for dry/faulty TDS
        field4="3",      # Fault severity
        field5="2.51",
        field6="4.20",
        field7="256",    # Bit 8: HEALTH_TDS_FAULT
        field8="0.142",  # Diagnostic voltage preserved
    )
    res = ThingSpeakService.process_and_save_feeds(isolated_db, [dry_fault_item])
    assert res.new_records_saved == 1

    rec = isolated_db.query(WaterReadingModel).filter_by(entry_id=701).one()
    assert rec.tds is None
    assert rec.tds_calibrated is False
    assert rec.tds_voltage == 0.142

    config = ModeService.get_or_create_config(isolated_db)
    ev = ModeService.evaluate_reading(rec, config)
    assert ev.parameter_evaluations["tds"].status == "fault"
    assert ev.violated_parameters == []  # Fault is NOT a water-quality threshold violation

    # Chatbot fallback must clearly distinguish raw voltage (0.142V) from missing ppm and note 25C limit
    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_get_llm_adapter", lambda: None)
    chat_resp = await agent.answer_query("What is my TDS right now?", isolated_db)
    assert "0.142 V" in chat_resp.response
    assert "Calibration Pending" in chat_resp.response or "null" in chat_resp.response
    assert "25" in chat_resp.response


@pytest.mark.asyncio
async def test_chatbot_refuses_tap_water_safety_when_uncalibrated(isolated_db, monkeypatch):
    """Chatbot must never claim uncalibrated tap water is certified or safe to drink."""
    from app.chatbot.agent import WaterChatbotAgent

    uncal_item = ThingSpeakFeedItem(
        entry_id=702,
        created_at=datetime.utcnow(),
        field1="",
        field2="",
        field3="",
        field4="0",
        field5="3.366",
        field6="0.238",
        field7="64",  # HEALTH_CALIBRATION_PENDING
        field8="0.142",
    )
    ThingSpeakService.process_and_save_feeds(isolated_db, [uncal_item])

    agent = WaterChatbotAgent()
    monkeypatch.setattr(agent, "_get_llm_adapter", lambda: None)
    resp = await agent.answer_query("Is this household tap water safe to drink?", isolated_db)
    low = resp.response.lower()
    assert "uncalibrated" in low
    assert "do not prove" in low or "not prove" in low
    assert "certified" in low or "laboratory" in low
