"""Pydantic schemas for alert events."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class AlertCreate(BaseModel):
    severity: int
    title: str
    message: str


class AlertResponse(BaseModel):
    id: int
    timestamp: datetime
    severity: int
    title: str
    message: str
    resolved: bool
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AlertSummaryResponse(BaseModel):
    total_active: int
    critical_count: int
    warning_count: int
    fault_count: int
    recent_alerts: List[AlertResponse]
