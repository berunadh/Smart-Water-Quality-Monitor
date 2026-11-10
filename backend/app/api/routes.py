"""Primary REST API routes for Phase 2 Smart Water Quality Monitor."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.session import get_db
from app.core.config import settings
from app.models.water_reading import WaterReadingModel
from app.models.alert_log import AlertLogModel
from app.models.calibration import CalibrationRecordModel
from app.schemas.sensor import (
    SensorReadingResponse,
    SensorStatsResponse,
    SystemHealthResponse,
    CalibrationRecordCreate,
    CalibrationRecordResponse,
    CalibrationStatusDetail,
)
from app.schemas.alert import AlertResponse, AlertSummaryResponse
from app.schemas.ml import AnomalyResponse, TrendResponse, MLSummaryResponse
from app.schemas.chat import ChatRequest, ChatResponse, ChatbotStatusResponse
from app.schemas.thingspeak import ThingSpeakSyncResult
from app.schemas.mode import (
    WaterQualityModeLiteral,
    WaterQualitySettingsResponse,
    ModeSwitchRequest,
    ThresholdUpdateRequest,
)
from app.services.thingspeak_service import ThingSpeakService
from app.services.demo_service import DemoService
from app.services.alert_service import AlertService
from app.services.mode_service import ModeService
from app.ml.anomaly_detector import RobustStatisticalDetector, IsolationForestDetector
from app.ml.fault_detector import SensorFaultDetector
from app.ml.trend_analyzer import TrendAnalyzer
from app.ml.insights import InsightsGenerator
from app.ml.trainer import ModelTrainer
from app.chatbot.agent import WaterChatbotAgent
import pandas as pd

api_router = APIRouter()
chatbot_agent = WaterChatbotAgent()


# ==============================================================================
# 1. SYSTEM HEALTH & DIAGNOSTICS
# ==============================================================================

@api_router.get("/health", response_model=Dict[str, Any], tags=["System Health"])
def get_backend_health(db: Session = Depends(get_db)):
    """
    Returns backend service health, operating mode (demo/real),
    cloud connectivity state, and last successful telemetry timestamp.
    """
    latest = (
        db.query(WaterReadingModel)
        .order_by(WaterReadingModel.timestamp.desc())
        .first()
    )

    last_sync = latest.timestamp if latest else None
    is_stale = False
    if last_sync:
        age_seconds = (datetime.utcnow() - last_sync).total_seconds()
        is_stale = (age_seconds > 300)

    cloud_status = "CONNECTED" if (latest and latest.data_source == "thingspeak" and not is_stale) else "IDLE"
    if settings.DATA_MODE == "demo":
        cloud_status = "DEMO_MODE (SIMULATED)"

    config = ModeService.get_or_create_config(db)

    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "operating_mode": settings.DATA_MODE,
        "water_quality_mode": config.active_mode,
        "cloud_connectivity": cloud_status,
        "last_successful_telemetry": last_sync.isoformat() if last_sync else None,
        "data_freshness": "STALE" if is_stale else "LIVE",
        "database_records_count": db.query(WaterReadingModel).count(),
    }


@api_router.get("/system/status", response_model=SystemHealthResponse, tags=["System Health"])
def get_system_status(db: Session = Depends(get_db)):
    """
    Decodes the 16-bit hardware health bitmask from the latest telemetry record,
    reporting sensor availability, electrical safety, and Wi-Fi state.
    """
    config = ModeService.get_or_create_config(db)
    latest = (
        db.query(WaterReadingModel)
        .order_by(WaterReadingModel.timestamp.desc())
        .first()
    )

    if not latest:
        if settings.DATA_MODE == "demo":
            DemoService.seed_demo_history(db, count=10)
            latest = db.query(WaterReadingModel).order_by(WaterReadingModel.timestamp.desc()).first()

    if not latest:
        return SystemHealthResponse(
            raw_code=0x0020,
            wifi_connected=False,
            cloud_synced=False,
            ph_sensor_healthy=True,
            turbidity_sensor_healthy=True,
            tds_sensor_healthy=True,
            electrical_safe=True,
            tds_installed=False,
            calibration_pending=True,
            demo_mode=(settings.DATA_MODE == "demo"),
            overall_status="AWAITING_TELEMETRY",
            operating_mode=settings.DATA_MODE,
            water_quality_mode=config.active_mode,
            data_freshness="NO_DATA",
            last_cloud_sync=None,
        )

    is_stale = (datetime.utcnow() - latest.timestamp).total_seconds() > 300
    return SystemHealthResponse.from_bitmask(
        code=latest.health_code,
        operating_mode=settings.DATA_MODE,
        last_sync=latest.timestamp,
        is_stale=is_stale,
        water_quality_mode=config.active_mode,
    )


# ==============================================================================
# 2. SENSOR READINGS & TELEMETRY
# ==============================================================================

@api_router.get("/readings/latest", response_model=Optional[SensorReadingResponse], tags=["Sensor Readings"])
def get_latest_reading(db: Session = Depends(get_db)):
    """
    Retrieves the most recent water reading with calibration status,
    voltages, sensor health, and data source provenance.
    """
    latest = (
        db.query(WaterReadingModel)
        .order_by(WaterReadingModel.timestamp.desc())
        .first()
    )

    if not latest and settings.DATA_MODE == "demo":
        DemoService.seed_demo_history(db, count=15)
        latest = db.query(WaterReadingModel).order_by(WaterReadingModel.timestamp.desc()).first()

    return latest


@api_router.get("/readings/history", response_model=List[SensorReadingResponse], tags=["Sensor Readings"])
def get_readings_history(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of historical records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    hours: Optional[int] = Query(None, ge=1, le=720, description="Filter records within past N hours"),
    valid_only: bool = Query(False, description="Exclude records with electrical or bounds faults"),
    db: Session = Depends(get_db),
):
    """
    Retrieves paginated historical water telemetry with optional time-range filtering.
    """
    query = db.query(WaterReadingModel)

    if hours:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(WaterReadingModel.timestamp >= cutoff)

    if valid_only:
        query = query.filter(WaterReadingModel.is_valid == True)

    total = query.count()
    if total == 0 and settings.DATA_MODE == "demo":
        DemoService.seed_demo_history(db, count=limit)
        query = db.query(WaterReadingModel)

    readings = (
        query.order_by(WaterReadingModel.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return readings


@api_router.get("/readings/statistics", response_model=SensorStatsResponse, tags=["Sensor Readings"])
def get_sensor_statistics(
    hours: int = Query(24, ge=1, le=720, description="Window in hours to calculate statistics"),
    db: Session = Depends(get_db),
):
    """Computes mean, min, and max summary metrics over the requested timeframe."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    total = (
        db.query(func.count(WaterReadingModel.id))
        .filter(WaterReadingModel.timestamp >= cutoff, WaterReadingModel.is_valid == True)
        .scalar() or 0
    )

    if total == 0:
        return SensorStatsResponse(
            count=0,
            operating_mode=settings.DATA_MODE,
            data_source="simulated" if settings.DATA_MODE == "demo" else "thingspeak",
            last_updated=datetime.utcnow(),
        )

    stats = (
        db.query(
            func.avg(WaterReadingModel.ph),
            func.min(WaterReadingModel.ph),
            func.max(WaterReadingModel.ph),
            func.avg(WaterReadingModel.turbidity),
            func.max(WaterReadingModel.turbidity),
            func.avg(WaterReadingModel.tds),
        )
        .filter(WaterReadingModel.timestamp >= cutoff, WaterReadingModel.is_valid == True)
        .first()
    )

    latest = db.query(WaterReadingModel).order_by(WaterReadingModel.timestamp.desc()).first()

    return SensorStatsResponse(
        count=total,
        operating_mode=settings.DATA_MODE,
        data_source=latest.data_source if latest else "unknown",
        ph_mean=round(stats[0], 2) if stats and stats[0] is not None else None,
        ph_min=round(stats[1], 2) if stats and stats[1] is not None else None,
        ph_max=round(stats[2], 2) if stats and stats[2] is not None else None,
        turbidity_mean=round(stats[3], 2) if stats and stats[3] is not None else None,
        turbidity_max=round(stats[4], 2) if stats and stats[4] is not None else None,
        tds_mean=round(stats[5], 1) if stats and stats[5] is not None else None,
        last_updated=latest.timestamp if latest else datetime.utcnow(),
    )


# ==============================================================================
# 3. ALERTS & INCIDENT LOGS
# ==============================================================================

@api_router.get("/alerts", response_model=AlertSummaryResponse, tags=["Alerts"])
def get_alerts(db: Session = Depends(get_db)):
    """Retrieves active alerts and recent incident history with severity levels."""
    return AlertService.get_alert_summary(db)


@api_router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse, tags=["Alerts"])
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Marks an active alert as acknowledged and resolved."""
    alert = db.query(AlertLogModel).filter(AlertLogModel.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert record not found")

    alert.resolved = True
    alert.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert


# ==============================================================================
# 4. THINGSPEAK CLOUD SYNCHRONIZATION
# ==============================================================================

@api_router.post("/thingspeak/sync", response_model=ThingSpeakSyncResult, tags=["ThingSpeak Cloud"])
async def sync_thingspeak(
    results: int = Query(50, ge=1, le=8000),
    db: Session = Depends(get_db),
):
    """
    Manually pulls the latest telemetry feed from ThingSpeak,
    validates data against the 7-field contract, and saves new records.
    """
    channel_id = str(settings.THINGSPEAK_CHANNEL_ID)
    if not channel_id or channel_id == "0" or channel_id == "YOUR_CHANNEL_ID":
        raise HTTPException(
            status_code=400,
            detail="ThingSpeak Channel ID is not configured. Set THINGSPEAK_CHANNEL_ID in backend/.env",
        )

    feed_response = await ThingSpeakService.fetch_feeds(
        channel_id=channel_id,
        read_api_key=settings.THINGSPEAK_READ_API_KEY,
        results=results,
    )

    if not feed_response:
        raise HTTPException(
            status_code=502,
            detail="Unable to reach ThingSpeak API or channel returned error.",
        )

    return ThingSpeakService.process_and_save_feeds(db, feed_response.feeds)


# ==============================================================================
# 5. MACHINE LEARNING & ANOMALIES
# ==============================================================================

@api_router.get("/ml/anomalies", response_model=AnomalyResponse, tags=["Machine Learning"])
def get_ml_anomalies(
    limit: int = Query(150, ge=10, le=1000),
    threshold: float = Query(3.0, ge=1.0, le=10.0),
    db: Session = Depends(get_db),
):
    """
    Runs multi-tier anomaly detection (Robust Statistical MAD + Isolation Forest + Fault Detector)
    over recent telemetry, detecting pH spikes, turbidity jumps, and hardware stuck values.
    """
    readings = (
        db.query(WaterReadingModel)
        .order_by(WaterReadingModel.timestamp.desc())
        .limit(limit)
        .all()
    )

    if not readings:
        if settings.DATA_MODE == "demo":
            DemoService.seed_demo_history(db, count=60)
            readings = db.query(WaterReadingModel).order_by(WaterReadingModel.timestamp.desc()).limit(limit).all()

    if not readings:
        return AnomalyResponse(analyzed_samples=0, anomaly_count=0, operating_mode=settings.DATA_MODE, anomalies=[])

    # Reverse to chronological order
    readings_chron = list(reversed(readings))
    df = pd.DataFrame([
        {
            "id": r.id,
            "timestamp": r.timestamp,
            "ph": r.ph,
            "turbidity": r.turbidity,
            "tds": r.tds,
            "ph_voltage": r.ph_voltage,
            "turbidity_voltage": r.turbidity_voltage,
            "tds_voltage": r.tds_voltage,
        }
        for r in readings_chron
    ])

    all_anomalies = []

    # 1. Hardware Fault Detector
    faults = SensorFaultDetector.analyze_faults(df)
    all_anomalies.extend(faults)

    # 2. Robust Statistical Detector
    stat_detector = RobustStatisticalDetector(z_threshold=threshold)
    stat_anomalies = stat_detector.predict(df)
    all_anomalies.extend(stat_anomalies)

    # 3. Isolation Forest Detector
    iso_detector = IsolationForestDetector()
    ml_anomalies = iso_detector.predict(df)
    all_anomalies.extend(ml_anomalies)

    return AnomalyResponse(
        analyzed_samples=len(df),
        anomaly_count=len(all_anomalies),
        operating_mode=settings.DATA_MODE,
        anomalies=all_anomalies,
    )


@api_router.get("/ml/trends", response_model=TrendResponse, tags=["Machine Learning"])
def get_ml_trends(
    limit: int = Query(150, ge=10, le=1000),
    db: Session = Depends(get_db),
):
    """Calculates linear degradation rates, R-squared fit, and baseline drift."""
    readings = (
        db.query(WaterReadingModel)
        .filter(WaterReadingModel.is_valid == True)
        .order_by(WaterReadingModel.timestamp.asc())
        .limit(limit)
        .all()
    )

    if not readings and settings.DATA_MODE == "demo":
        DemoService.seed_demo_history(db, count=50)
        readings = db.query(WaterReadingModel).filter(WaterReadingModel.is_valid == True).order_by(WaterReadingModel.timestamp.asc()).limit(limit).all()

    data = [
        {
            "timestamp": r.timestamp,
            "ph": r.ph,
            "turbidity": r.turbidity,
            "tds": r.tds,
        }
        for r in readings
    ]
    df = pd.DataFrame(data)
    return TrendAnalyzer.evaluate_water_trends(df, operating_mode=settings.DATA_MODE)


@api_router.get("/ml/summary", response_model=MLSummaryResponse, tags=["Machine Learning"])
def get_ml_summary(db: Session = Depends(get_db)):
    """
    Synthesizes current readings, trends, and anomalies into structured,
    categorized AI explanations (MEASURED_FACT, STATISTICAL_ANOMALY, ML_PREDICTION, RULE_BASED_WARNING).
    """
    return InsightsGenerator.generate_summary(db, operating_mode=settings.DATA_MODE)


@api_router.post("/ml/train", tags=["Machine Learning"])
def train_ml_model(db: Session = Depends(get_db)):
    """
    Triggers model training workflow. Uses historical telemetry if >= 50 valid records exist,
    otherwise benchmarks on controlled synthetic baseline datasets.
    """
    valid_count = db.query(WaterReadingModel).filter(WaterReadingModel.is_valid == True).count()
    if valid_count >= 50:
        result = ModelTrainer.retrain_from_database(db)
    else:
        result = ModelTrainer.train_baseline_model()
    return result


# ==============================================================================
# 6. AI ADVISOR CHATBOT
# ==============================================================================

@api_router.post("/chat", response_model=ChatResponse, tags=["AI Chatbot"])
async def chat_with_advisor(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Conversational water quality consultant. Evaluates resident inquiries using
    real-time sensor telemetry, 24-hour historical statistics, active alerts, and EPA/WHO standards.
    """
    return await chatbot_agent.answer_query(
        query=request.message,
        db=db,
        session_id=request.session_id or "default_session",
    )


@api_router.get("/chatbot/status", response_model=ChatbotStatusResponse, tags=["AI Chatbot"])
def get_chatbot_status():
    """
    Returns the configured AI Chatbot provider, model, and operational status
    without exposing credentials.
    """
    return chatbot_agent.get_provider_status()


# ==============================================================================
# 7. DEMO SCENARIO CONTROL
# ==============================================================================

@api_router.post("/demo/inject/{scenario}", response_model=SensorReadingResponse, tags=["Demo Mode"])
def inject_demo_scenario(scenario: str, db: Session = Depends(get_db)):
    """
    Injects a specific scenario ('normal', 'warning', 'critical', 'uncalibrated', 'sensor_fault', 'stale')
    into the database, evaluated dynamically under the currently selected Water Quality Mode.
    """
    try:
        config = ModeService.get_or_create_config(db)
        reading = DemoService.generate_demo_reading(scenario=scenario, config=config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.add(reading)
    db.commit()
    db.refresh(reading)

    AlertService.evaluate_and_record_alerts(db, reading)

    return reading


# ==============================================================================
# 8. SENSOR CALIBRATION MANAGEMENT
# ==============================================================================

@api_router.get("/calibration/status", response_model=CalibrationStatusDetail, tags=["Sensor Calibration"])
def get_calibration_status(db: Session = Depends(get_db)):
    """
    Returns current calibration state of all probes, active raw voltages,
    required reference standards, and recent logged calibration events.
    """
    latest = (
        db.query(WaterReadingModel)
        .order_by(WaterReadingModel.timestamp.desc())
        .first()
    )

    records = (
        db.query(CalibrationRecordModel)
        .order_by(CalibrationRecordModel.timestamp.desc())
        .limit(10)
        .all()
    )

    ph_cal = latest.ph_calibrated if latest else False
    turb_cal = latest.turbidity_calibrated if latest else False
    tds_cal = latest.tds_calibrated if latest else False
    ph_v = latest.ph_voltage if latest else 0.0
    turb_v = latest.turbidity_voltage if latest else 0.0
    tds_v = latest.tds_voltage if latest else None

    return CalibrationStatusDetail(
        ph_calibrated=ph_cal,
        turbidity_calibrated=turb_cal,
        tds_calibrated=tds_cal,
        calibration_pending=(not ph_cal or not turb_cal or not tds_cal),
        ph_voltage=ph_v,
        turbidity_voltage=turb_v,
        tds_voltage=tds_v,
        ph_reference_standards=["pH 7.00 (Neutral Buffer)", "pH 4.01 (Acidic Buffer)"],
        turbidity_reference_standards=["0.0 NTU (Distilled Baseline)", "100.0 NTU (Certified Standard)"],
        tds_reference_standards=["342 mg/L (NaCl Reference)", "707 mg/L (1413 uS/cm KCl Standard)"],
        recent_records=[CalibrationRecordResponse.model_validate(r) for r in records],
    )


@api_router.post("/calibration/record", response_model=CalibrationRecordResponse, tags=["Sensor Calibration"])
def log_calibration_record(record_in: CalibrationRecordCreate, db: Session = Depends(get_db)):
    """
    Logs an official sensor calibration event into the database for compliance and traceability.
    """
    record = CalibrationRecordModel(
        sensor_type=record_in.sensor_type,
        point_name=record_in.point_name,
        reference_value=record_in.reference_value,
        measured_voltage=record_in.measured_voltage,
        operator_notes=record_in.operator_notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@api_router.get("/calibration/records", response_model=List[CalibrationRecordResponse], tags=["Sensor Calibration"])
def get_calibration_records(
    sensor_type: Optional[str] = Query(None, description="Filter by 'ph', 'turbidity', or 'tds'"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Retrieves historical calibration records.
    """
    query = db.query(CalibrationRecordModel)
    if sensor_type:
        query = query.filter(CalibrationRecordModel.sensor_type == sensor_type)
    return query.order_by(CalibrationRecordModel.timestamp.desc()).limit(limit).all()


# ==============================================================================
# 9. DUAL WATER QUALITY MODES & THRESHOLD CONFIGURATION
# ==============================================================================

@api_router.get("/settings/mode", response_model=WaterQualitySettingsResponse, tags=["Water Quality Modes"])
def get_water_quality_settings(db: Session = Depends(get_db)):
    """
    Returns active Water Quality Mode ('drinking' or 'regular_usage'), both separate
    threshold profiles, and real-time evaluation of the latest telemetry reading.
    """
    return ModeService.get_settings_response(db)


@api_router.put("/settings/mode", response_model=WaterQualitySettingsResponse, tags=["Water Quality Modes"])
def set_water_quality_mode(req: ModeSwitchRequest, db: Session = Depends(get_db)):
    """
    Persists mode change ('drinking' or 'regular_usage') and immediately recalculates
    parameter status and threshold alerts.
    """
    return ModeService.switch_mode(db, req.mode)


@api_router.put("/settings/thresholds", response_model=WaterQualitySettingsResponse, tags=["Water Quality Modes"])
def update_mode_thresholds(req: ThresholdUpdateRequest, db: Session = Depends(get_db)):
    """
    Updates configurable threshold bounds for a specific mode without affecting the other mode.
    """
    return ModeService.update_thresholds(db, req)


@api_router.post("/settings/mode/reset/{mode}", response_model=WaterQualitySettingsResponse, tags=["Water Quality Modes"])
def reset_mode_thresholds(mode: WaterQualityModeLiteral, db: Session = Depends(get_db)):
    """
    Restores default limits for the selected mode (Drinking: BIS IS 10500:2012; Regular Usage: defaults).
    """
    return ModeService.reset_mode_defaults(db, mode)


