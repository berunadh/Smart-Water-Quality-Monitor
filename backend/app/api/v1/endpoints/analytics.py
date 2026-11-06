"""Machine learning and trend analytics endpoints."""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
import pandas as pd

from app.database.session import get_db
from app.models.water_reading import WaterReadingModel
from app.ml.pipeline import WaterFeaturePipeline
from app.ml.anomaly_detector import ZScoreAnomalyDetector
from app.ml.trend_analyzer import TrendAnalyzer

router = APIRouter()


@router.get("/trends")
def get_water_trends(
    limit: int = Query(200, ge=10, le=2000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Calculates linear drift rates and trend directions for pH and Turbidity."""
    readings = (
        db.query(WaterReadingModel)
        .filter(WaterReadingModel.is_valid == True)
        .order_by(WaterReadingModel.timestamp.asc())
        .limit(limit)
        .all()
    )

    if not readings:
        return {"status": "NO_DATA", "message": "Insufficient data to compute trends."}

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
    return TrendAnalyzer.evaluate_water_trends(df)


@router.get("/anomalies")
def detect_anomalies(
    limit: int = Query(200, ge=10, le=2000),
    threshold: float = Query(3.0, ge=1.0, le=10.0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Runs statistical moving Z-Score anomaly detection on recent telemetry."""
    readings = (
        db.query(WaterReadingModel)
        .order_by(WaterReadingModel.timestamp.asc())
        .limit(limit)
        .all()
    )

    if not readings:
        return {"status": "NO_DATA", "anomalies": []}

    data = [
        {
            "id": r.id,
            "timestamp": r.timestamp,
            "ph": r.ph,
            "turbidity": r.turbidity,
            "ph_board_voltage": r.ph_board_voltage,
            "turbidity_board_voltage": r.turbidity_board_voltage,
        }
        for r in readings
    ]
    df = pd.DataFrame(data)

    detector = ZScoreAnomalyDetector(threshold=threshold)
    anomalies = detector.predict(df)

    return {
        "analyzed_samples": len(df),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }
