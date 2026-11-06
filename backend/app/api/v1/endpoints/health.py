"""System health and diagnostic endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.water_reading import WaterReadingModel
from app.schemas.sensor import SystemHealthResponse
from app.core.config import settings

router = APIRouter()


@router.get("", response_model=SystemHealthResponse)
def get_system_health(db: Session = Depends(get_db)):
    """
    Decodes the 16-bit hardware health bitmask from the most recent telemetry entry.
    """
    latest = (
        db.query(WaterReadingModel)
        .order_by(WaterReadingModel.timestamp.desc())
        .first()
    )

    if not latest:
        # Default starting state if no telemetry has been ingested
        return SystemHealthResponse(
            raw_code=0,
            wifi_connected=False,
            cloud_synced=False,
            ph_sensor_healthy=True,
            turbidity_sensor_healthy=True,
            electrical_safe=True,
            tds_installed=False,
            calibration_pending=True,
            demo_mode=False,
            overall_status="AWAITING_TELEMETRY",
        )

    return SystemHealthResponse.from_bitmask(latest.health_code)
