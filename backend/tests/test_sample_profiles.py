"""Regression tests for honest three-water presentation profile telemetry."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.sample_profile import SampleProfileStateModel
from app.services.sample_profile_service import SampleProfileService


def test_reference_profiles_keep_actual_voltages_and_never_fake_sensor_ph():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        state = SampleProfileService.get_or_create(db)
        ro = SampleProfileService.make_reading(state)
        assert ro.sample_profile == "kent_ro"
        assert ro.ph_voltage == 4.770
        assert ro.turbidity_voltage == 0.939
        assert ro.tds_voltage == 0.307
        assert ro.ph_sensor_estimate is None
        assert ro.ph_display_source == "DEMO_ESTIMATE"
        assert 0.3 <= ro.turbidity <= 1.0
        assert ro.health_code & (1 << 12)  # pH provisional / response suspect

        state.selected_profile = "household_tap"
        tap = SampleProfileService.make_reading(state)
        assert tap.ph_voltage == 4.770
        assert tap.turbidity_voltage == 1.484
        assert tap.tds_voltage == 2.155
        assert 1.0 <= tap.turbidity <= 5.0
        assert tap.turbidity > ro.turbidity
        assert tap.ph_sensor_estimate is None
    finally:
        db.close()


def test_contaminated_demo_ph_is_explicit_and_adjustable():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        state = SampleProfileService.get_or_create(db)
        state.selected_profile = "contaminated_demo"
        state.contaminated_demo_ph = 4.6
        reading = SampleProfileService.make_reading(state)
        assert reading.ph == 4.6
        assert reading.ph_demo_estimate == 4.6
        assert reading.ph_sensor_estimate is None
        assert "salt/dirt" in reading.validation_notes.lower()
    finally:
        db.close()
