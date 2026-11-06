"""Unit tests for ThingSpeak telemetry parsing."""

import pytest
from datetime import datetime
from app.services.validation_service import ValidationService
from app.schemas.thingspeak import ThingSpeakFeedItem


def test_thingspeak_feed_parsing():
    feed = ThingSpeakFeedItem(
        entry_id=101,
        created_at=datetime.utcnow(),
        field1="7.42",
        field2="1.8",
        field3="",            # Missing TDS left empty
        field4="0",           # Normal
        field5="2.450",       # pH board voltage
        field6="4.120",       # Turbidity board voltage
        field7="32",          # Health code (Bit 5 set = TDS unavailable)
    )

    ph = ValidationService.parse_float_field(feed.field1)
    turb = ValidationService.parse_float_field(feed.field2)
    tds = ValidationService.parse_float_field(feed.field3)
    sev = ValidationService.parse_int_field(feed.field4)
    ph_v = ValidationService.parse_float_field(feed.field5)
    turb_v = ValidationService.parse_float_field(feed.field6)
    health = ValidationService.parse_int_field(feed.field7)

    assert ph == 7.42
    assert turb == 1.8
    assert tds is None   # Crucial: Empty string MUST parse to None, NEVER 0.0
    assert sev == 0
    assert ph_v == 2.450
    assert turb_v == 4.120
    assert health == 32
