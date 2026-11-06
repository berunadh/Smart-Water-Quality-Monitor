"""Sensor readings endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.session import get_db
from app.models.water_reading import WaterReadingModel
from app.schemas.sensor import SensorReadingResponse, SensorStatsResponse

router = APIRouter()


@router.get("/latest", response_model=Optional[SensorReadingResponse])
def get_latest_reading(db: Session = Depends(get_db)):
    """Retrieves the most recent water reading recorded in the database."""
    reading = (
        db.query(WaterReadingModel)
        .order_by(WaterReadingModel.timestamp.desc())
        .first()
    )
    return reading


@router.get("/history", response_model=List[SensorReadingResponse])
def get_reading_history(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    valid_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Retrieves paginated historical sensor readings."""
    query = db.query(WaterReadingModel)
    if valid_only:
        query = query.filter(WaterReadingModel.is_valid == True)

    readings = (
        query.order_by(WaterReadingModel.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return readings


@router.get("/statistics", response_model=SensorStatsResponse)
def get_sensor_statistics(db: Session = Depends(get_db)):
    """Computes aggregate summary statistics for water quality parameters."""
    total = db.query(func.count(WaterReadingModel.id)).scalar() or 0

    if total == 0:
        return SensorStatsResponse(count=0)

    stats = (
        db.query(
            func.avg(WaterReadingModel.ph),
            func.min(WaterReadingModel.ph),
            func.max(WaterReadingModel.ph),
            func.avg(WaterReadingModel.turbidity),
            func.max(WaterReadingModel.turbidity),
            func.avg(WaterReadingModel.tds),
        )
        .filter(WaterReadingModel.is_valid == True)
        .first()
    )

    return SensorStatsResponse(
        count=total,
        ph_mean=round(stats[0], 2) if stats and stats[0] is not None else None,
        ph_min=round(stats[1], 2) if stats and stats[1] is not None else None,
        ph_max=round(stats[2], 2) if stats and stats[2] is not None else None,
        turbidity_mean=round(stats[3], 2) if stats and stats[3] is not None else None,
        turbidity_max=round(stats[4], 2) if stats and stats[4] is not None else None,
        tds_mean=round(stats[5], 1) if stats and stats[5] is not None else None,
    )
