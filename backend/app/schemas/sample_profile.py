"""Schemas for the presentation sample profiles."""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

SampleProfile = Literal["kent_ro", "household_tap", "contaminated_demo"]


class SampleProfileStateResponse(BaseModel):
    selected_profile: SampleProfile
    contaminated_demo_ph: float = Field(ge=0.0, le=14.0)
    updated_at: datetime
    control_note: str


class SampleProfileUpdateRequest(BaseModel):
    selected_profile: SampleProfile
    contaminated_demo_ph: Optional[float] = Field(None, ge=0.0, le=14.0)
