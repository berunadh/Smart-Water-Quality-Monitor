"""SQLAlchemy model for physical and telemetry water sensor readings."""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, Boolean, String, DateTime, Index
from app.database.base import Base


class WaterReadingModel(Base):
    __tablename__ = "water_readings"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, unique=True, index=True, nullable=True)  # ThingSpeak entry ID (null for demo)
    device_id = Column(String(64), default="esp32-water-monitor-01", index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)

    # Physical / Calibrated measurements (Nullable if uncalibrated or absent)
    ph = Column(Float, nullable=True)                  # Calibrated pH (e.g. 6.5 - 8.5)
    turbidity = Column(Float, nullable=True)           # Calibrated Turbidity in NTU
    tds = Column(Float, nullable=True)                 # Calibrated TDS in ppm (STRICT: NULL if uncalibrated)

    # Sensor Board / ADC Voltages
    # pH & Turbidity use 15k/10k voltage divider (reconstructed V_board = V_ADC * 2.50)
    # TDS uses direct 3.3V ADC input (V_ADC directly, NO divider multiplier)
    ph_voltage = Column(Float, nullable=False)
    turbidity_voltage = Column(Float, nullable=False)
    tds_voltage = Column(Float, nullable=True)

    # Calibration Status Flags for Each Sensor
    ph_calibrated = Column(Boolean, default=False, nullable=False)
    turbidity_calibrated = Column(Boolean, default=False, nullable=False)
    tds_calibrated = Column(Boolean, default=False, nullable=False)

    # Diagnostic Telemetry and Health Bitmask
    alert_severity = Column(Integer, default=0, nullable=False)  # 0=Normal, 1=Warn, 2=Crit, 3=Fault
    health_code = Column(Integer, default=0, nullable=False)     # 16-bit system health bitmask
    sensor_health_summary = Column(String(64), default="OPERATIONAL", nullable=False)
    alert_messages = Column(String(255), default="NORMAL", nullable=False)

    # Operational Provenance & Water Quality Evaluation Mode
    data_source = Column(String(32), default="thingspeak", nullable=False)  # "thingspeak" | "simulated" | "sensor_node"
    operating_mode = Column(String(16), default="real", nullable=False)     # "real" | "demo"
    water_quality_mode = Column(String(32), default="drinking", nullable=False)  # "drinking" | "regular_usage"
    is_valid = Column(Boolean, default=True, nullable=False)
    is_stale = Column(Boolean, default=False, nullable=False)
    validation_notes = Column(String(255), nullable=True)

    __table_args__ = (
        Index("idx_reading_device_time", "device_id", "timestamp"),
        Index("idx_reading_valid_time", "is_valid", "timestamp"),
    )
