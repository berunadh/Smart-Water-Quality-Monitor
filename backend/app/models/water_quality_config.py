"""SQLAlchemy model for persistent Water Quality Mode and Threshold profiles."""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime
from app.database.base import Base


class WaterQualityConfigModel(Base):
    """
    Stores the persistent active water quality mode ('drinking' or 'regular_usage')
    and completely separate threshold profiles for both modes.
    """
    __tablename__ = "water_quality_config"

    id = Column(Integer, primary_key=True, default=1)
    active_mode = Column(String(32), default="drinking", nullable=False)

    # Drinking Mode: Indian Standard BIS IS 10500:2012 Acceptable Limits
    drinking_ph_min = Column(Float, default=6.5, nullable=False)
    drinking_ph_max = Column(Float, default=8.5, nullable=False)
    drinking_turbidity_max = Column(Float, default=1.0, nullable=False)
    drinking_tds_max = Column(Float, default=500.0, nullable=False)

    # Regular Usage Mode: Separate configurable non-drinking operational defaults
    regular_ph_min = Column(Float, default=6.0, nullable=False)
    regular_ph_max = Column(Float, default=9.0, nullable=False)
    regular_turbidity_max = Column(Float, default=10.0, nullable=False)
    regular_tds_max = Column(Float, default=1000.0, nullable=False)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
