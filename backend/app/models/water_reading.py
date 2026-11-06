"""SQLAlchemy model for physical water sensor readings."""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, Boolean, String, DateTime
from app.database.base import Base


class WaterReadingModel(Base):
    __tablename__ = "water_readings"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, unique=True, index=True, nullable=True)  # ThingSpeak entry ID
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)

    # Physical / Calibrated measurements (Nullable if uncalibrated or absent)
    ph = Column(Float, nullable=True)                  # Calibrated pH (e.g. 6.5 - 8.5)
    turbidity = Column(Float, nullable=True)           # Calibrated Turbidity in NTU
    tds = Column(Float, nullable=True)                 # Calibrated TDS in ppm (NULL if not installed)

    # Telemetry and Diagnostic Metrics
    alert_severity = Column(Integer, default=0, nullable=False)  # 0=Normal, 1=Warn, 2=Crit, 3=Fault
    ph_board_voltage = Column(Float, nullable=False)             # Reconstructed sensor board V
    turbidity_board_voltage = Column(Float, nullable=False)      # Reconstructed sensor board V
    health_code = Column(Integer, default=0, nullable=False)     # 16-bit system health bitmask

    # Data Quality & Validation
    is_valid = Column(Boolean, default=True, nullable=False)
    validation_notes = Column(String(255), nullable=True)
