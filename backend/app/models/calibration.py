"""SQLAlchemy model for probe calibration records."""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime
from app.database.base import Base


class CalibrationRecordModel(Base):
    __tablename__ = "calibration_records"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    sensor_type = Column(String(32), nullable=False)    # "ph", "turbidity", "tds"
    point_name = Column(String(32), nullable=False)     # "pH_7.00", "pH_4.01", "turb_clear_0NTU"
    reference_value = Column(Float, nullable=False)     # Known standard value
    measured_voltage = Column(Float, nullable=False)    # Sensor board output voltage
    operator_notes = Column(String(255), nullable=True)
