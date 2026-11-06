"""Pydantic schemas for ThingSpeak feed parsing and telemetry serialization."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ThingSpeakFeedItem(BaseModel):
    entry_id: int
    created_at: datetime
    # Telemetry fields as string from ThingSpeak API (may be None / empty string)
    field1: Optional[str] = Field(None, description="Calibrated pH")
    field2: Optional[str] = Field(None, description="Calibrated Turbidity (NTU)")
    field3: Optional[str] = Field(None, description="Calibrated TDS (ppm, None if uninstalled)")
    field4: Optional[str] = Field(None, description="Alert Severity (0-3)")
    field5: Optional[str] = Field(None, description="pH Board Output Voltage (V)")
    field6: Optional[str] = Field(None, description="Turbidity Board Output Voltage (V)")
    field7: Optional[str] = Field(None, description="System Health Bitmask")


class ThingSpeakChannelMeta(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_entry_id: Optional[int] = None


class ThingSpeakFeedResponse(BaseModel):
    channel: ThingSpeakChannelMeta
    feeds: List[ThingSpeakFeedItem]


class ThingSpeakSyncResult(BaseModel):
    channel_id: str
    total_fetched: int
    new_records_saved: int
    validation_failures: int
    latest_entry_id: Optional[int] = None
