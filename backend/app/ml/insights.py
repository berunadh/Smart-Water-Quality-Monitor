"""AI Insights Generator.
Synthesizes telemetry, trends, anomalies, and faults into human-readable,
strictly categorized explanations.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session

from app.models.water_reading import WaterReadingModel
from app.models.alert_log import AlertLogModel
from app.schemas.ml import MLSummaryResponse, TrendResponse
from app.ml.anomaly_detector import RobustStatisticalDetector, IsolationForestDetector
from app.ml.fault_detector import SensorFaultDetector
from app.ml.trend_analyzer import TrendAnalyzer


class InsightsGenerator:
    """
    Generates structured, human-readable insights categorized into:
    - MEASURED_FACT
    - STATISTICAL_ANOMALY
    - ML_PREDICTION
    - RULE_BASED_WARNING
    """

    @classmethod
    def generate_summary(cls, db: Session, operating_mode: str = "real") -> MLSummaryResponse:
        readings = (
            db.query(WaterReadingModel)
            .order_by(WaterReadingModel.timestamp.desc())
            .limit(150)
            .all()
        )

        insights: List[Dict[str, str]] = []

        if not readings:
            insights.append({
                "type": "MEASURED_FACT",
                "message": "No sensor readings are currently stored in the database.",
            })
            return MLSummaryResponse(
                status="NO_DATA",
                operating_mode=operating_mode,
                total_records=0,
                active_anomalies_count=0,
                dominant_trend="NO_DATA",
                insights=insights,
                model_metadata={"status": "NO_MODEL"},
            )

        # Convert to DataFrame (reverse so chronological)
        readings_chron = list(reversed(readings))
        df = pd.DataFrame([
            {
                "timestamp": r.timestamp,
                "ph": r.ph,
                "turbidity": r.turbidity,
                "tds": r.tds,
                "ph_voltage": r.ph_voltage,
                "turbidity_voltage": r.turbidity_voltage,
                "tds_voltage": r.tds_voltage,
                "alert_severity": r.alert_severity,
                "is_valid": r.is_valid,
                "is_stale": r.is_stale,
            }
            for r in readings_chron
        ])

        latest = readings[0]

        # 1. MEASURED FACTS
        ph_str = f"{latest.ph:.2f}" if latest.ph is not None else "Uncalibrated / Pending"
        turb_str = f"{latest.turbidity:.1f} NTU" if latest.turbidity is not None else "Uncalibrated / Pending"
        if latest.tds is not None:
            tds_str = f"{latest.tds:.0f} mg/L"
        elif latest.tds_voltage is not None and not latest.tds_calibrated:
            tds_str = f"Uncalibrated (ADC {latest.tds_voltage:.3f}V)"
        else:
            tds_str = "Uncalibrated / Unavailable"

        insights.append({
            "type": "MEASURED_FACT",
            "category": "MEASURED_FACT",
            "message": f"Latest telemetry at {latest.timestamp.strftime('%H:%M:%S UTC')}: pH = {ph_str}, Turbidity = {turb_str}, TDS = {tds_str}.",
        })

        if latest.is_stale:
            insights.append({
                "type": "RULE_BASED_WARNING",
                "category": "RULE_BASED_WARNING",
                "message": "Telemetry stream is stale. Last transmission was more than 5 minutes ago.",
            })

        # 2. HARDWARE FAULTS
        faults = SensorFaultDetector.analyze_faults(df)
        for fault in faults:
            insights.append({
                "type": "RULE_BASED_WARNING",
                "category": "RULE_BASED_WARNING",
                "parameter": fault.parameter,
                "message": fault.human_explanation,
            })

        # 3. TREND INSIGHTS
        trend_resp: TrendResponse = TrendAnalyzer.evaluate_water_trends(df, operating_mode=operating_mode)
        if trend_resp.turbidity_drift.trend_direction == "INCREASING":
            insights.append({
                "type": "MEASURED_FACT",
                "category": "MEASURED_FACT",
                "parameter": "turbidity",
                "message": (
                    f"Turbidity is rising at a measured rate of {trend_resp.turbidity_drift.slope_per_hour:+.2f} NTU/hour."
                ),
            })
        elif trend_resp.turbidity_drift.trend_direction == "STABLE":
            insights.append({
                "type": "MEASURED_FACT",
                "category": "MEASURED_FACT",
                "parameter": "turbidity",
                "message": "Turbidity baseline remained stable over the monitored window.",
            })

        if trend_resp.ph_drift.trend_direction not in ("STABLE", "INSUFFICIENT_DATA", "NO_DATA"):
            insights.append({
                "type": "MEASURED_FACT",
                "category": "MEASURED_FACT",
                "parameter": "ph",
                "message": f"pH trend is {trend_resp.ph_drift.trend_direction.lower()} ({trend_resp.ph_drift.slope_per_hour:+.3f} units/hour).",
            })

        if trend_resp.tds_drift and trend_resp.tds_drift.trend_direction not in ("STABLE", "INSUFFICIENT_DATA", "NO_DATA"):
            insights.append({
                "type": "MEASURED_FACT",
                "category": "MEASURED_FACT",
                "parameter": "tds",
                "message": f"TDS trend is {trend_resp.tds_drift.trend_direction.lower()} ({trend_resp.tds_drift.slope_per_hour:+.1f} ppm/hour).",
            })

        # 4. STATISTICAL ANOMALIES
        stat_detector = RobustStatisticalDetector()
        stat_anomalies = stat_detector.predict(df)
        for a in stat_anomalies[-3:]:
            insights.append({
                "type": "STATISTICAL_ANOMALY",
                "category": "STATISTICAL_ANOMALY",
                "parameter": a.parameter,
                "message": a.human_explanation,
            })

        # 5. ML PREDICTIONS (Isolation Forest)
        iso_detector = IsolationForestDetector()
        ml_anomalies = iso_detector.predict(df)
        for a in ml_anomalies[-2:]:
            insights.append({
                "type": "ML_PREDICTION",
                "category": "ML_PREDICTION",
                "parameter": a.parameter,
                "message": a.human_explanation,
            })

        insights.append({
            "type": "RULE_BASED_WARNING",
            "category": "RULE_BASED_WARNING",
            "message": "ML anomaly detection flags statistical deviations only; it does not certify water potability.",
        })

        total_anomalies = len(faults) + len(stat_anomalies) + len(ml_anomalies)
        dominant_trend = trend_resp.turbidity_drift.trend_direction

        return MLSummaryResponse(
            status="OPERATIONAL",
            operating_mode=operating_mode,
            total_records=len(readings),
            active_anomalies_count=total_anomalies,
            dominant_trend=dominant_trend,
            insights=insights,
            model_metadata=iso_detector.metadata or {"status": "INITIALIZING"},
        )
