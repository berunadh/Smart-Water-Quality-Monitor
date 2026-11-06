"""Unit tests for Demo Mode simulation scenarios and TDS null invariant."""

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


def test_demo_scenarios_tds_strictly_null():
    """TDS must be strictly None across all demo scenarios, never 0.0."""
    scenarios = ["normal", "warning", "critical", "sensor_fault", "stale"]

    for sc in scenarios:
        reading = DemoService.generate_demo_reading(scenario=sc)
        assert reading.tds is None, f"Scenario '{sc}' violated TDS null invariant!"
        assert reading.tds_calibrated is False
        assert reading.data_source == "simulated"
        assert reading.operating_mode == "demo"


def test_demo_warning_and_critical_severities():
    """Warning scenario must have severity=1; critical scenario must have severity=2."""
    warn_reading = DemoService.generate_demo_reading(scenario="warning")
    assert warn_reading.alert_severity == 1
    assert "TURBIDITY" in warn_reading.alert_messages

    crit_reading = DemoService.generate_demo_reading(scenario="critical")
    assert crit_reading.alert_severity == 2
    assert "CRITICAL" in crit_reading.alert_messages


def test_demo_sensor_fault_scenario():
    """Sensor fault scenario must flag is_valid=False and severity=3."""
    fault_reading = DemoService.generate_demo_reading(scenario="sensor_fault")
    assert fault_reading.is_valid is False
    assert fault_reading.alert_severity == 3
    assert fault_reading.ph is None
    assert fault_reading.turbidity is None


def test_demo_seeding(memory_db):
    """Demo seeding must create requested number of records and handle TDS properly."""
    created = DemoService.seed_demo_history(memory_db, count=25)
    assert created == 25
    assert memory_db.query(WaterReadingModel).count() == 25

    # Verify all records have data_source='simulated' and tds=None
    all_readings = memory_db.query(WaterReadingModel).all()
    for r in all_readings:
        assert r.tds is None
        assert r.data_source == "simulated"
        assert r.operating_mode == "demo"
