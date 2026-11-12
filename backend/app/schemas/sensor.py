"""Pydantic schemas for sensor data serialization, validation, and analytics."""

from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, ConfigDict, computed_field, model_validator


CalibrationConfidence = Literal[
    "VERIFIED_CALIBRATION",
    "MODEL_BASED_PROVISIONAL",
    "DEMONSTRATION_ESTIMATE",
    "UNCALIBRATED",
    "SENSOR_FAULT",
]


class SensorCalibrationStatus(BaseModel):
    ph_calibrated: bool = False
    turbidity_calibrated: bool = False
    tds_calibrated: bool = False


class SensorReadingBase(BaseModel):
    device_id: str = Field("esp32-water-monitor-01", description="Unique identifier of the IoT sensor node")
    ph: Optional[float] = Field(None, ge=0.0, le=14.0, description="Calibrated pH reading (0.0 to 14.0, null if uncalibrated)")
    ph_sensor_estimate: Optional[float] = Field(None, ge=0.0, le=14.0, description="Physical pH-interface estimate only; null when response is suspect")
    ph_demo_estimate: Optional[float] = Field(None, ge=0.0, le=14.0, description="Explicit presentation-only pH estimate; never a sensor measurement")
    ph_display_source: str = Field("SENSOR_ESTIMATE", description="SENSOR_ESTIMATE or DEMO_ESTIMATE")
    turbidity: Optional[float] = Field(None, ge=0.0, description="Calibrated Turbidity in NTU (null if uncalibrated)")
    tds: Optional[float] = Field(None, ge=0.0, description="Calibrated TDS in ppm (STRICT: null when uninstalled)")
    ph_voltage: float = Field(..., ge=0.0, description="pH signal board output voltage (V)")
    turbidity_voltage: float = Field(..., ge=0.0, description="Turbidity signal board output voltage (V)")
    tds_voltage: Optional[float] = Field(None, ge=0.0, description="TDS direct ADC input voltage on GPIO35 (V, no divider)")
    ph_board_voltage: Optional[float] = Field(None, description="Alias for ph_voltage")
    turbidity_board_voltage: Optional[float] = Field(None, description="Alias for turbidity_voltage")
    ph_calibrated: bool = Field(False, description="True only if pH probe has undergone two-point buffer calibration")
    turbidity_calibrated: bool = Field(False, description="True only if optical probe has undergone baseline calibration")
    tds_calibrated: bool = Field(False, description="True only if TDS probe has undergone reference standard calibration")
    alert_severity: int = Field(0, ge=0, le=3, description="0=Normal, 1=Warning, 2=Critical, 3=Fault")
    alert_messages: str = Field("NORMAL", description="Active alert banner or message")
    sensor_health_summary: str = Field("OPERATIONAL", description="Human-readable health status")
    health_code: int = Field(0, description="16-bit System health bitmask")
    data_source: str = Field("thingspeak", description="'thingspeak', 'simulated', or 'sensor_node'")
    operating_mode: str = Field("real", description="'real' or 'demo'")
    water_quality_mode: str = Field("drinking", description="'drinking' or 'regular_usage'")
    sample_profile: str = Field("live", description="live, kent_ro, household_tap, or contaminated_demo")
    is_valid: bool = Field(True, description="True if passes electrical safety and physical plausibility bounds")
    is_stale: bool = Field(False, description="True if reading timestamp exceeds freshness threshold")

    def _confidence_for(self, calibrated: bool, provisional_bit: int, fault_bit: int) -> CalibrationConfidence:
        """Expose the firmware's calibration provenance without changing telemetry fields."""
        if (not self.is_valid) or bool(self.health_code & (1 << 4)) or bool(self.health_code & (1 << fault_bit)):
            return "SENSOR_FAULT"
        if self.operating_mode == "demo" or bool(self.health_code & (1 << 7)):
            return "DEMONSTRATION_ESTIMATE"
        if calibrated:
            return "VERIFIED_CALIBRATION"
        if bool(self.health_code & (1 << provisional_bit)):
            return "MODEL_BASED_PROVISIONAL"
        return "UNCALIBRATED"

    @computed_field
    @property
    def ph_calibration_status(self) -> CalibrationConfidence:
        return self._confidence_for(self.ph_calibrated, 12, 2)

    @computed_field
    @property
    def turbidity_calibration_status(self) -> CalibrationConfidence:
        return self._confidence_for(self.turbidity_calibrated, 13, 3)

    @computed_field
    @property
    def tds_calibration_status(self) -> CalibrationConfidence:
        return self._confidence_for(self.tds_calibrated, 11, 8)

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
    tds_sensor_healthy: bool = True
    tds_dry: bool = False
    tds_provisional: bool = False
    ph_provisional: bool = False
    turb_provisional: bool = False
    electrical_safe: bool
    tds_installed: bool
    calibration_pending: bool
    demo_mode: bool
    overall_status: str
    operating_mode: str
    water_quality_mode: str = "drinking"
    data_freshness: str
    last_cloud_sync: Optional[datetime] = None

    @classmethod
    def from_bitmask(
        cls, 
        code: int, 
        operating_mode: str = "real",
        last_sync: Optional[datetime] = None,
        is_stale: bool = False,
        water_quality_mode: str = "drinking",
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
        # Bit 8: HEALTH_TDS_FAULT
        # Bit 9: HEALTH_MODE_REGULAR
        # Bit 10: HEALTH_TDS_DRY
        # Bit 11: HEALTH_TDS_PROVISIONAL
        # Bit 12: HEALTH_PH_PROVISIONAL
        # Bit 13: HEALTH_TURB_PROVISIONAL
        wifi_ok = not bool(code & (1 << 0))
        cloud_ok = not bool(code & (1 << 1))
        ph_ok = not bool(code & (1 << 2))
        turb_ok = not bool(code & (1 << 3))
        tds_ok = not bool(code & (1 << 8))
        tds_dry = bool(code & (1 << 10))
        tds_prov = bool(code & (1 << 11))
        ph_prov = bool(code & (1 << 12))
        turb_prov = bool(code & (1 << 13))
        safe = not bool(code & (1 << 4))
        tds_present = not bool(code & (1 << 5))
        cal_pending = bool(code & (1 << 6))
        demo = bool(code & (1 << 7)) or (operating_mode == "demo")

        if not safe:
            status = "ELECTRICAL HAZARD"
        elif not ph_ok or not turb_ok or not tds_ok:
            status = "SENSOR FAULT"
        elif is_stale:
            status = "STALE DATA"
        elif tds_dry:
            status = "TDS PROBE DRY"
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
            tds_sensor_healthy=tds_ok,
            tds_dry=tds_dry,
            tds_provisional=tds_prov,
            ph_provisional=ph_prov,
            turb_provisional=turb_prov,
            electrical_safe=safe,
            tds_installed=tds_present,
            calibration_pending=cal_pending,
            demo_mode=demo,
            overall_status=status,
            operating_mode=operating_mode,
            water_quality_mode=water_quality_mode,
            data_freshness=freshness,
            last_cloud_sync=last_sync,
        )


class CalibrationRecordCreate(BaseModel):
    sensor_type: str = Field(..., description="'ph', 'turbidity', or 'tds'")
    point_name: str = Field(..., description="e.g. 'pH_7.00', 'pH_4.01', 'turb_0NTU', 'turb_100NTU'")
    reference_value: float = Field(..., description="Known reference value (pH or NTU)")
    measured_voltage: float = Field(..., ge=0.0, description="Measured board output voltage in V")
    operator_notes: Optional[str] = None


class CalibrationRecordResponse(BaseModel):
    id: int
    timestamp: datetime
    sensor_type: str
    point_name: str
    reference_value: float
    measured_voltage: float
    operator_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CalibrationStatusDetail(BaseModel):
    ph_calibrated: bool
    turbidity_calibrated: bool
    tds_calibrated: bool
    ph_provisional: bool = False
    turbidity_provisional: bool = False
    tds_provisional: bool = False
    calibration_pending: bool
    ph_voltage: float
    turbidity_voltage: float
    tds_voltage: Optional[float] = None
    ph_reference_standards: List[str]
    turbidity_reference_standards: List[str]
    tds_reference_standards: List[str] = []
    recent_records: List[CalibrationRecordResponse]

