"""SQLAlchemy model for persistent ML anomaly records."""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Index
from app.database.base import Base


class MLAnomalyRecordModel(Base):
    __tablename__ = "ml_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    parameter = Column(String(32), nullable=False)           # "ph", "turbidity", "multivariate"
    measured_value = Column(Float, nullable=True)
    baseline_mean = Column(Float, nullable=True)
    baseline_std = Column(Float, nullable=True)
    anomaly_score = Column(Float, nullable=False)
    detector_type = Column(String(32), nullable=False)       # "zscore", "isolation_forest", "mad"
    anomaly_type = Column(String(64), nullable=False)        # "STATISTICAL_SPIKE_PH", "MULTIVARIATE_ISOLATION_ANOMALY"
    human_explanation = Column(String(255), nullable=False)

    __table_args__ = (
        Index("idx_anomaly_param_time", "parameter", "timestamp"),
    )
