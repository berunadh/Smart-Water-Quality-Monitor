"""Tests for Water Quality Score (WQS), Critical Hazard Override, and ThingSpeak 5-field option."""

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from app.database.base import Base
from app.models.water_reading import WaterReadingModel
from app.schemas.thingspeak import ThingSpeakFeedItem
from app.services.mode_service import ModeService
from app.services.thingspeak_service import ThingSpeakService
from app.services.wqs_service import (
    WqsService,
    compute_subindex_ph,
    compute_subindex_tds,
    compute_subindex_turbidity,
)


@pytest.fixture
def wqs_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_wqs_exact_weights_and_subindices(wqs_db):
    """WQS = 0.40 * q_TDS + 0.35 * q_pH + 0.25 * q_Turb when all 3 sensors are valid."""
    config = ModeService.get_or_create_config(wqs_db)
    reading = WaterReadingModel(
        ph=7.00,
        turbidity=0.50,
        tds=200.0,
        ph_voltage=2.50,
        turbidity_voltage=4.20,
        tds_voltage=1.05,
        ph_calibrated=True,
        turbidity_calibrated=True,
        tds_calibrated=True,
        health_code=0,
        is_valid=True,
    )
    ev = ModeService.evaluate_reading(reading, config)
    expected = round(
        0.40 * round(compute_subindex_tds(200.0), 2)
        + 0.35 * round(compute_subindex_ph(7.00), 2)
        + 0.25 * round(compute_subindex_turbidity(0.50), 2),
        2,
    )
    assert ev.wqs == pytest.approx(expected, abs=0.05)
    assert ev.water_status_code == 4
    assert ev.water_status_label == "Nominal"
    assert ev.critical_hazard is False


def test_missing_sensor_keeps_wqs_unavailable(wqs_db):
    """If any sensor is missing/uncalibrated/faulty, WQS stays None and no hazard fires."""
    config = ModeService.get_or_create_config(wqs_db)
    reading = WaterReadingModel(
        ph=7.20,
        turbidity=None,
        tds=220.0,
        ph_voltage=2.50,
        turbidity_voltage=0.02,
        tds_voltage=1.05,
        ph_calibrated=True,
        turbidity_calibrated=False,
        tds_calibrated=True,
        health_code=(1 << 3),  # HEALTH_TURB_FAULT (disconnected)
        is_valid=True,
    )
    ev = ModeService.evaluate_reading(reading, config)
    assert ev.wqs is None
    assert ev.critical_hazard is False
    assert ev.water_status_code == -1
    assert ev.overall_status == "SENSOR_FAULT"


@pytest.mark.parametrize(
    "ph,turb,tds,alert_msg",
    [
        (4.80, 0.40, 150.0, "NORMAL"),        # Critical pH < 5.0
        (9.70, 0.40, 150.0, "NORMAL"),        # Critical pH > 9.5
        (7.10, 0.40, 750.0, "NORMAL"),        # Critical TDS > 700 ppm
        (7.10, 165.0, 150.0, "NORMAL"),       # Critical Turbidity > 150 NTU
    ],
)
def test_critical_hazard_override_caps_wqs_and_sets_status_zero(wqs_db, ph, turb, tds, alert_msg):
    """Critical thresholds force water_status_code=0, cap WQS <= 20.0, and set CRITICAL."""
    config = ModeService.get_or_create_config(wqs_db)
    reading = WaterReadingModel(
        ph=ph,
        turbidity=turb,
        tds=tds,
        ph_voltage=2.50,
        turbidity_voltage=3.20,
        tds_voltage=1.80,
        ph_calibrated=True,
        turbidity_calibrated=True,
        tds_calibrated=True,
        health_code=0,
        alert_messages=alert_msg,
        is_valid=True,
    )
    ev = ModeService.evaluate_reading(reading, config)
    assert ev.critical_hazard is True
    assert ev.water_status_code == 0
    assert ev.water_status_label == "Hazard"
    assert ev.wqs is not None and ev.wqs <= 20.0
    assert ev.alert_severity == 2
    assert ev.overall_status == "CRITICAL"


def test_turbidity_outside_calibration_range_triggers_hazard_only_when_healthy():
    """Healthy turbidity out-of-calibration-range triggers hazard; disconnected fault does not."""
    haz = WqsService.evaluate(
        ph_valid=True,
        ph=7.10,
        turb_valid=False,
        turbidity=None,
        tds_valid=True,
        tds=180.0,
        turb_out_of_cal_range=True,
        any_hardware_fault=False,
    )
    assert haz.critical_hazard is True
    assert haz.water_status_code == 0
    assert haz.wqs is None

    disc = WqsService.evaluate(
        ph_valid=True,
        ph=7.10,
        turb_valid=False,
        turbidity=None,
        tds_valid=True,
        tds=180.0,
        turb_out_of_cal_range=False,
        any_hardware_fault=True,
    )
    assert disc.critical_hazard is False
    assert disc.water_status_code == -1


def test_thingspeak_optional_5field_profile_parsing(wqs_db):
    """Optional 5-field mapping (field1=TDS, field2=pH, field3=Turb, field4=WQS, field5=Status)."""
    item = ThingSpeakFeedItem(
        entry_id=9001,
        created_at=datetime.utcnow(),
        field1="245",
        field2="7.22",
        field3="0.8",
        field4="91.5",
        field5="4",
    )
    res = ThingSpeakService.process_and_save_feeds(wqs_db, [item], field_profile="5field")
    assert res.new_records_saved == 1
    rec = wqs_db.query(WaterReadingModel).filter_by(entry_id=9001).one()
    assert rec.tds == 245.0
    assert rec.ph == 7.22
    assert rec.turbidity == 0.8
    assert rec.alert_severity == 0


def test_health_flags_distinguish_dry_disconnected_provisional_and_pending(wqs_db):
    """Verify dry probe (0x0400), disconnected turb (0x0008), and provisional TDS (0x0800) are distinct."""
    from app.schemas.sensor import SystemHealthResponse

    config = ModeService.get_or_create_config(wqs_db)
    now = datetime.utcnow()

    # 1. Dry TDS probe (bit 10) + disconnected turbidity (bit 3, 0.12V board) + pH pending (bit 6)
    items = [
        ThingSpeakFeedItem(
            entry_id=9101,
            created_at=now,
            field1="",
            field2="",
            field3="",
            field4="3",
            field5="3.372",
            field6="0.120",
            field7=str((1 << 3) | (1 << 6) | (1 << 10)),
            field8="0.142",
        ),
        ThingSpeakFeedItem(
            entry_id=9102,
            created_at=now,
            field1="7.15",
            field2="0.6",
            field3="210",
            field4="0",
            field5="2.51",
            field6="4.20",
            field7=str(1 << 11),  # HEALTH_TDS_PROVISIONAL
            field8="1.050",
        ),
    ]
    res = ThingSpeakService.process_and_save_feeds(wqs_db, items)
    assert res.new_records_saved == 2

    rec1 = wqs_db.query(WaterReadingModel).filter_by(entry_id=9101).one()
    ev1 = ModeService.evaluate_reading(rec1, config)
    assert ev1.parameter_evaluations["ph"].status == "uncalibrated"
    assert ev1.parameter_evaluations["turbidity"].status == "disconnected"
    assert ev1.parameter_evaluations["tds"].status == "dry"
    assert ev1.wqs is None
    assert ev1.critical_hazard is False

    h1 = SystemHealthResponse.from_bitmask(rec1.health_code)
    assert h1.tds_dry is True
    assert h1.tds_sensor_healthy is True  # Dry is NOT a hardware fault
    assert h1.turbidity_sensor_healthy is False

    rec2 = wqs_db.query(WaterReadingModel).filter_by(entry_id=9102).one()
    assert rec2.tds == 210.0
    assert rec2.tds_calibrated is False  # Provisional model does NOT falsely claim calibrated
    ev2 = ModeService.evaluate_reading(rec2, config)
    assert ev2.wqs is not None
    assert ev2.water_status_code in (3, 4)
    assert ev2.water_status_label in ("Good", "Nominal")
    h2 = SystemHealthResponse.from_bitmask(rec2.health_code)
    assert h2.tds_provisional is True


def test_thingspeak_utc_z_timestamp_and_provisional_ph_turb_flags(wqs_db):
    """UTC 'Z' timestamps ingest cleanly without TypeError; bits 11/12/13 keep experimental cal separate."""
    from datetime import timezone
    from app.schemas.sensor import SystemHealthResponse

    config = ModeService.get_or_create_config(wqs_db)
    utc_z_feed = ThingSpeakFeedItem.model_validate({
        "entry_id": 165,
        "created_at": "2026-11-11T08:33:10Z",
        "field1": None,
        "field2": None,
        "field3": "155",
        "field4": "0",
        "field5": "3.906",
        "field6": "0.886",
        "field7": "2112",  # 0x0840 = HEALTH_TDS_PROVISIONAL | HEALTH_CALIBRATION_PENDING
    })
    prov_all_feed = ThingSpeakFeedItem.model_validate({
        "entry_id": 166,
        "created_at": "2026-11-11T08:35:00Z",
        "field1": "7.05",
        "field2": "0.5",
        "field3": "160",
        "field4": "0",
        "field5": "2.490",
        "field6": "3.995",
        "field7": str((1 << 6) | (1 << 11) | (1 << 12) | (1 << 13)),
    })

    res = ThingSpeakService.process_and_save_feeds(wqs_db, [utc_z_feed, prov_all_feed])
    assert res.new_records_saved == 2

    rec165 = wqs_db.query(WaterReadingModel).filter_by(entry_id=165).one()
    assert rec165.timestamp.tzinfo is None
    assert rec165.tds == 155.0
    assert rec165.tds_calibrated is False
    ev165 = ModeService.evaluate_reading(rec165, config)
    assert ev165.parameter_evaluations["tds"].status == "acceptable"
    assert ev165.parameter_evaluations["tds"].value == 155.0

    rec166 = wqs_db.query(WaterReadingModel).filter_by(entry_id=166).one()
    assert rec166.ph == 7.05
    assert rec166.turbidity == 0.5
    assert rec166.tds == 160.0
    assert rec166.ph_calibrated is False
    assert rec166.turbidity_calibrated is False
    assert rec166.tds_calibrated is False

    ev166 = ModeService.evaluate_reading(rec166, config)
    assert ev166.parameter_evaluations["ph"].value == 7.05
    assert ev166.parameter_evaluations["turbidity"].value == 0.5
    assert ev166.parameter_evaluations["tds"].value == 160.0
    assert ev166.overall_status == "CALIBRATION_PENDING"
    # Model estimates remain visible but cannot be treated as a calibrated WQS
    # or a critical hazard until physical standards are recorded.
    assert ev166.parameter_evaluations["ph"].status == "provisional"
    assert ev166.parameter_evaluations["turbidity"].status == "provisional"
    assert ev166.wqs is None
    assert ev166.critical_hazard is False

    h166 = SystemHealthResponse.from_bitmask(rec166.health_code)
    assert h166.ph_provisional is True
    assert h166.turb_provisional is True
    assert h166.tds_provisional is True
    assert h166.calibration_pending is True


def test_provisional_ph_and_turbidity_are_visible_but_non_alerting(wqs_db):
    """The 8-field telemetry contract preserves Field 2 NTU verbatim without promoting provisional values to hazards."""
    config = ModeService.get_or_create_config(wqs_db)
    item = ThingSpeakFeedItem(
        entry_id=9170,
        created_at=datetime.utcnow(),
        field1="7.10",         # Provisional pH display value
        field2="3.20",         # Field 2 corrected provisional NTU at 1.484V board
        field3="210",
        field4="0",            # Firmware validator keeps provisional values non-alerting
        field5="4.770",
        field6="1.484",
        field7=str((1 << 6) | (1 << 11) | (1 << 12) | (1 << 13)),
        field8="1.050",
    )
    assert ThingSpeakService.process_and_save_feeds(wqs_db, [item]).new_records_saved == 1

    record = wqs_db.query(WaterReadingModel).filter_by(entry_id=9170).one()
    assert record.ph == pytest.approx(7.10)
    assert record.turbidity == pytest.approx(3.20)
    assert record.turbidity_voltage == pytest.approx(1.484)
    assert record.ph_calibrated is False
    assert record.turbidity_calibrated is False

    evaluation = ModeService.evaluate_reading(record, config)
    assert evaluation.parameter_evaluations["ph"].status == "provisional"
    assert evaluation.parameter_evaluations["turbidity"].status == "provisional"
    assert evaluation.parameter_evaluations["turbidity"].value == pytest.approx(3.20)
    assert evaluation.overall_status == "CALIBRATION_PENDING"
    assert evaluation.critical_hazard is False
