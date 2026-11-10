"""Pydantic schemas for Machine Learning and AI insights."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AnomalyItem(BaseModel):
    timestamp: Optional[datetime] = None
    parameter: str = Field(..., description="Sensor parameter (ph, turbidity, or multivariate)")
    measured_value: Optional[float] = None
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None
    anomaly_score: float
    detector_type: str = Field(..., description="'zscore', 'isolation_forest', or 'mad'")
    anomaly_type: str
    human_explanation: str
    category: str = Field("STATISTICAL_ANOMALY", description="Classification of the insight")


class AnomalyResponse(BaseModel):
    analyzed_samples: int
    anomaly_count: int
    operating_mode: str
    anomalies: List[AnomalyItem]


class TrendItem(BaseModel):
    parameter: str
    slope_per_hour: float
    intercept: Optional[float] = None
    r_squared: float
    trend_direction: str  # "INCREASING", "DECREASING", "STABLE", "INSUFFICIENT_DATA"
    explanation: str


class TrendResponse(BaseModel):
    status: str
    operating_mode: str
    ph_drift: TrendItem
    turbidity_drift: TrendItem
    tds_drift: Optional[TrendItem] = None
    total_samples: int


class MLSummaryResponse(BaseModel):
    status: str
    operating_mode: str
    total_records: int
    active_anomalies_count: int
    dominant_trend: str
    insights: List[Dict[str, str]] = Field(
        ...,
        description="List of human-readable insights categorized as MEASURED_FACT, STATISTICAL_ANOMALY, ML_PREDICTION, or RULE_BASED_WARNING",
    )
    model_metadata: Dict[str, Any]
