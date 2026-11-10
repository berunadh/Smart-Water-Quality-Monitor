"""Unit tests for Demo Mode simulation scenarios and TDS calibrated vs uncalibrated invariants."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.water_reading import WaterReadingModel
from app.services.demo_service import DemoService


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_demo_uncalibrated_and_fault_tds_strictly_null():
    """Uncalibrated and fault scenarios must keep calibrated values strictly None, never 0.0."""
    for sc in ["uncalibrated", "sensor_fault"]:
        reading = DemoService.generate_demo_reading(scenario=sc)
        assert reading.tds is None, f"Scenario '{sc}' violated TDS null invariant!"
        assert reading.ph is None
        assert reading.turbidity is None
        assert reading.tds_calibrated is False
        assert reading.data_source == "simulated"
        assert reading.operating_mode == "demo"


def test_demo_calibrated_tds_and_severities():
    """Calibrated demo scenarios populate realistic TDS (without 2.5x scaling) and correct severities."""
    norm = DemoService.generate_demo_reading(scenario="normal")
    assert norm.alert_severity == 0
    assert norm.tds is not None and 100.0 < norm.tds < 500.0
    assert norm.tds_voltage is not None and 0.3 < norm.tds_voltage < 3.0

    warn = DemoService.generate_demo_reading(scenario="warning")
    assert warn.alert_severity == 1
    assert "TURBIDITY" in warn.alert_messages and "TDS" in warn.alert_messages

    crit = DemoService.generate_demo_reading(scenario="critical")
    assert crit.alert_severity == 2
    assert "CRITICAL" in crit.alert_messages


def test_demo_seeding(memory_db):
    """Demo seeding creates requested records with simulated provenance and TDS telemetry."""
    created = DemoService.seed_demo_history(memory_db, count=25)
    assert created == 25
    assert memory_db.query(WaterReadingModel).count() == 25

    all_readings = memory_db.query(WaterReadingModel).all()
    for r in all_readings:
        assert r.data_source == "simulated"
        assert r.operating_mode == "demo"
        assert r.tds_voltage is not None
