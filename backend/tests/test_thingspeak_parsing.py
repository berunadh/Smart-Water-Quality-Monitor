"""Unit tests for ThingSpeak telemetry feed parsing, duplicate prevention, and TDS null integrity."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.water_reading import WaterReadingModel
from app.schemas.thingspeak import ThingSpeakFeedItem
from app.services.thingspeak_service import ThingSpeakService
from app.services.validation_service import ValidationService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_missing_tds_field_parsing():
    """Missing TDS field must parse strictly to None, NEVER to 0.0."""
    item = ThingSpeakFeedItem(
        entry_id=1,
        created_at=datetime.utcnow(),
        field1="7.35",
        field2="1.2",
        field3="",            # Missing TDS sent as empty string by ESP32
        field4="0",
        field5="2.560",
        field6="4.150",
        field7="32",          # Bit 5 set = HEALTH_TDS_UNAVAILABLE
    )

    tds_val = ValidationService.parse_float_field(item.field3)
    assert tds_val is None

    # Test with string literal "null" or "N/A"
    assert ValidationService.parse_float_field("null") is None
    assert ValidationService.parse_float_field("N/A") is None
    assert ValidationService.parse_float_field("none") is None


def test_uncalibrated_measurements_parsing():
    """Uncalibrated pH and Turbidity sent as empty strings must remain None."""
    item = ThingSpeakFeedItem(
        entry_id=2,
        created_at=datetime.utcnow(),
        field1="",            # Omitted because probe is uncalibrated
        field2="",            # Omitted because probe is uncalibrated
        field3="",
        field4="0",
        field5="2.480",       # Uncalibrated voltage present
        field6="4.220",       # Uncalibrated voltage present
        field7="64",          # Bit 6 set = HEALTH_CALIBRATION_PENDING
    )

    ph = ValidationService.parse_float_field(item.field1)
    turb = ValidationService.parse_float_field(item.field2)
    assert ph is None
    assert turb is None
    assert ValidationService.parse_float_field(item.field5) == 2.480
    assert ValidationService.parse_float_field(item.field6) == 4.220


def test_duplicate_records_prevention(db_session):
    """ThingSpeak polling must not insert duplicate entries for identical entry_id."""
    now = datetime.utcnow()
    items = [
        ThingSpeakFeedItem(
            entry_id=100,
            created_at=now,
            field1="7.25",
            field2="0.8",
            field3=None,
            field4="0",
            field5="2.50",
            field6="4.20",
            field7="32",
        ),
        ThingSpeakFeedItem(
            entry_id=101,
            created_at=now,
            field1="7.26",
            field2="0.9",
            field3=None,
            field4="0",
            field5="2.51",
            field6="4.18",
            field7="32",
        ),
    ]

    # First sync inserts 2 records
    result1 = ThingSpeakService.process_and_save_feeds(db_session, items)
    assert result1.new_records_saved == 2
    assert db_session.query(WaterReadingModel).count() == 2

    # Second sync with identical items must insert 0 duplicates
    result2 = ThingSpeakService.process_and_save_feeds(db_session, items)
    assert result2.new_records_saved == 0
    assert db_session.query(WaterReadingModel).count() == 2


@pytest.mark.asyncio
async def test_thingspeak_invalid_channel_or_unreachable():
    """Unconfigured or invalid channel ID must return None without raising uncaught exceptions."""
    result = await ThingSpeakService.fetch_feeds(channel_id="0")
    assert result is None

    result_default = await ThingSpeakService.fetch_feeds(channel_id="YOUR_CHANNEL_ID")
    assert result_default is None
