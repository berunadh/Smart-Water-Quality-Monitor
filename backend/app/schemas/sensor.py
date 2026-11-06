"""Pydantic schemas for sensor data serialization, validation, and analytics."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SensorReadingBase(BaseModel):
    ph: Optional[float] = Field(None, ge=0.0, le=14.0, description="Calibrated pH reading (0.0 to 14.0)")
    turbidity: Optional[float] = Field(None, ge=0.0, description="Calibrated Turbidity in NTU")
    tds: Optional[float] = Field(None, ge=0.0, description="Calibrated TDS in ppm (None if uninstalled)")
    alert_severity: int = Field(0, ge=0, le=3, description="0=Normal, 1=Warning, 2=Critical, 3=Fault")
    ph_board_voltage: float = Field(..., ge=0.0, description="pH signal board output voltage (V)")
    turbidity_board_voltage: float = Field(..., ge=0.0, description="Turbidity signal board output voltage (V)")
    health_code: int = Field(0, description="16-bit System health bitmask")


class SensorReadingCreate(SensorReadingBase):
    entry_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    is_valid: bool = True
    validation_notes: Optional[str] = None


class SensorReadingResponse(SensorReadingBase):
    id: int
    entry_id: Optional[int] = None
    timestamp: datetime
    is_valid: bool
    validation_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SensorStatsResponse(BaseModel):
    count: int
    ph_mean: Optional[float] = None
    ph_min: Optional[float] = None
    ph_max: Optional[float] = None
    turbidity_mean: Optional[float] = None
    turbidity_max: Optional[float] = None
    tds_mean: Optional[float] = None


class SystemHealthResponse(BaseModel):
    raw_code: int
    wifi_connected: bool
    cloud_synced: bool
    ph_sensor_healthy: bool
    turbidity_sensor_healthy: bool
    electrical_safe: bool
    tds_installed: bool
    calibration_pending: bool
    demo_mode: bool
    overall_status: str

    @classmethod
    def from_bitmask(cls, code: int) -> "SystemHealthResponse":
        # Health bitmask mirrors config.h:
        # Bit 0: HEALTH_WIFI_DISCONNECTED
        # Bit 1: HEALTH_CLOUD_ERROR
        # Bit 2: HEALTH_PH_FAULT
        # Bit 3: HEALTH_TURB_FAULT
        # Bit 4: HEALTH_ADC_OVER_RANGE
        # Bit 5: HEALTH_TDS_UNAVAILABLE
        # Bit 6: HEALTH_CALIBRATION_PENDING
        # Bit 7: HEALTH_DEMO_MODE_ACTIVE
        wifi_ok = not bool(code & (1 << 0))
        cloud_ok = not bool(code & (1 << 1))
        ph_ok = not bool(code & (1 << 2))
        turb_ok = not bool(code & (1 << 3))
        safe = not bool(code & (1 << 4))
        tds_present = not bool(code & (1 << 5))
        cal_pending = bool(code & (1 << 6))
        demo = bool(code & (1 << 7))

        if not safe:
            status = "ELECTRICAL HAZARD"
        elif not ph_ok or not turb_ok:
            status = "SENSOR FAULT"
        elif cal_pending:
            status = "CALIBRATION PENDING"
        else:
            status = "OPERATIONAL"

        return cls(
            raw_code=code,
            wifi_connected=wifi_ok,
            cloud_synced=cloud_ok,
            ph_sensor_healthy=ph_ok,
            turbidity_sensor_healthy=turb_ok,
            electrical_safe=safe,
            tds_installed=tds_present,
            calibration_pending=cal_pending,
            demo_mode=demo,
            overall_status=status,
        )
