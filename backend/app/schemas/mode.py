"""Pydantic schemas for Dual Water Quality Modes (Drinking vs Regular Usage) and Evaluations."""

from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


WaterQualityModeLiteral = Literal["drinking", "regular_usage"]


class ModeThresholdProfile(BaseModel):
    ph_min: float = Field(..., ge=0.0, le=14.0)
    ph_max: float = Field(..., ge=0.0, le=14.0)
    turbidity_max: float = Field(..., gt=0.0, le=3000.0)
    tds_max: float = Field(..., gt=0.0, le=5000.0)
    label: str
    reference_note: str
    is_regulatory_reference: bool

    @model_validator(mode="after")
    def validate_ph_bounds(self) -> "ModeThresholdProfile":
        if self.ph_min >= self.ph_max:
            raise ValueError("ph_min must be strictly less than ph_max")
        return self


class ThresholdUpdateRequest(BaseModel):
    mode: WaterQualityModeLiteral
    ph_min: float = Field(..., ge=0.0, le=14.0)
    ph_max: float = Field(..., ge=0.0, le=14.0)
    turbidity_max: float = Field(..., gt=0.0, le=3000.0)
    tds_max: float = Field(..., gt=0.0, le=5000.0)

    @model_validator(mode="after")
    def validate_ph_bounds(self) -> "ThresholdUpdateRequest":
        if self.ph_min >= self.ph_max:
            raise ValueError("ph_min must be strictly less than ph_max")
        return self


class ModeSwitchRequest(BaseModel):
    mode: WaterQualityModeLiteral


class ParameterEvaluation(BaseModel):
    parameter: str
    status: str  # "acceptable" | "warning" | "exceeded" | "uncalibrated" | "unavailable" | "fault"
    value: Optional[float] = None
    unit: str
    limit_text: str
    message: str


class WaterQualityEvaluation(BaseModel):
    active_mode: WaterQualityModeLiteral
    mode_label: str
    overall_status: str  # "NORMAL" | "WARNING" | "EXCEEDED" | "CRITICAL" | "CALIBRATION_PENDING" | "SENSOR_FAULT" | "NO_DATA"
    alert_severity: int
    violated_parameters: List[str]
    parameter_evaluations: Dict[str, ParameterEvaluation]
    preliminary_disclaimer: str


class WaterQualitySettingsResponse(BaseModel):
    active_mode: WaterQualityModeLiteral
    active_profile: ModeThresholdProfile
    drinking_profile: ModeThresholdProfile
    regular_usage_profile: ModeThresholdProfile
    preliminary_disclaimer: str
    updated_at: datetime
    latest_evaluation: Optional[WaterQualityEvaluation] = None
