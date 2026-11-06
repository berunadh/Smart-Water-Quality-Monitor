"""Pydantic schemas for sensor data serialization, validation, and analytics."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict, model_validator


class SensorCalibrationStatus(BaseModel):
    ph_calibrated: bool = False
    turbidity_calibrated: bool = False
    tds_calibrated: bool = False


class SensorReadingBase(BaseModel):
    device_id: str = Field("esp32-water-monitor-01", description="Unique identifier of the IoT sensor node")
    ph: Optional[float] = Field(None, ge=0.0, le=14.0, description="Calibrated pH reading (0.0 to 14.0, null if uncalibrated)")
    turbidity: Optional[float] = Field(None, ge=0.0, description="Calibrated Turbidity in NTU (null if uncalibrated)")
    tds: Optional[float] = Field(None, ge=0.0, description="Calibrated TDS in ppm (STRICT: null when uninstalled)")
    ph_voltage: float = Field(..., ge=0.0, description="pH signal board output voltage (V)")
    turbidity_voltage: float = Field(..., ge=0.0, description="Turbidity signal board output voltage (V)")
    ph_board_voltage: Optional[float] = Field(None, description="Alias for ph_voltage")
    turbidity_board_voltage: Optional[float] = Field(None, description="Alias for turbidity_voltage")
    ph_calibrated: bool = Field(False, description="True only if pH probe has undergone two-point buffer calibration")
    turbidity_calibrated: bool = Field(False, description="True only if optical probe has undergone baseline calibration")
    tds_calibrated: bool = Field(False, description="TDS calibration status (false in Phase 1)")
    alert_severity: int = Field(0, ge=0, le=3, description="0=Normal, 1=Warning, 2=Critical, 3=Fault")
    alert_messages: str = Field("NORMAL", description="Active alert banner or message")
    sensor_health_summary: str = Field("OPERATIONAL", description="Human-readable health status")
    health_code: int = Field(0, description="16-bit System health bitmask")
    data_source: str = Field("thingspeak", description="'thingspeak', 'simulated', or 'sensor_node'")
    operating_mode: str = Field("real", description="'real' or 'demo'")
    is_valid: bool = Field(True, description="True if passes electrical safety and physical plausibility bounds")
    is_stale: bool = Field(False, description="True if reading timestamp exceeds freshness threshold")

    @model_validator(mode="before")
    @classmethod
    def map_voltage_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "ph_board_voltage" in data and "ph_voltage" not in data:
                data["ph_voltage"] = data["ph_board_voltage"]
            elif "ph_voltage" in data and "ph_board_voltage" not in data:
                data["ph_board_voltage"] = data["ph_voltage"]

            if "turbidity_board_voltage" in data and "turbidity_voltage" not in data:
                data["turbidity_voltage"] = data["turbidity_board_voltage"]
            elif "turbidity_voltage" in data and "turbidity_board_voltage" not in data:
                data["turbidity_board_voltage"] = data["turbidity_voltage"]
        return data


class SensorReadingCreate(SensorReadingBase):
    entry_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    validation_notes: Optional[str] = None


class SensorReadingResponse(SensorReadingBase):
    id: int
    entry_id: Optional[int] = None
    timestamp: datetime
    validation_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SensorStatsResponse(BaseModel):
    count: int
    operating_mode: str = "real"
    data_source: str = "thingspeak"
    ph_mean: Optional[float] = None
    ph_min: Optional[float] = None
    ph_max: Optional[float] = None
    turbidity_mean: Optional[float] = None
    turbidity_max: Optional[float] = None
    tds_mean: Optional[float] = None
    last_updated: Optional[datetime] = None


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
    operating_mode: str
    data_freshness: str
    last_cloud_sync: Optional[datetime] = None

    @classmethod
    def from_bitmask(
        cls, 
        code: int, 
        operating_mode: str = "real",
        last_sync: Optional[datetime] = None,
        is_stale: bool = False
    ) -> "SystemHealthResponse":
        # Health bitmask:
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
        demo = bool(code & (1 << 7)) or (operating_mode == "demo")

        if not safe:
            status = "ELECTRICAL HAZARD"
        elif not ph_ok or not turb_ok:
            status = "SENSOR FAULT"
        elif is_stale:
            status = "STALE DATA"
        elif cal_pending:
            status = "CALIBRATION PENDING"
        else:
            status = "OPERATIONAL"

        freshness = "STALE" if is_stale else "LIVE"

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
            operating_mode=operating_mode,
            data_freshness=freshness,
            last_cloud_sync=last_sync,
        )
