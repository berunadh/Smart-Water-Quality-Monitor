"""Persistent, explicitly-labelled presentation sample-profile state."""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime
from app.database.base import Base


class SampleProfileStateModel(Base):
    __tablename__ = "sample_profile_state"

    id = Column(Integer, primary_key=True, default=1)
    selected_profile = Column(String(32), default="kent_ro", nullable=False)
    contaminated_demo_ph = Column(Float, default=6.20, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
