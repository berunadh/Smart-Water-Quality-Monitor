"""SQLAlchemy model for alert events and incident tracking."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database.base import Base


class AlertLogModel(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    severity = Column(Integer, nullable=False)           # 1=Warning, 2=Critical, 3=Sensor Fault
    title = Column(String(64), nullable=False)           # e.g. "HIGH TURBIDITY", "pH OUT OF RANGE"
    message = Column(String(255), nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
