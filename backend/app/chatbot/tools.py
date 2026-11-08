"""Tool definitions for LLM context retrieval and water domain reasoning."""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.water_reading import WaterReadingModel
from app.models.alert_log import AlertLogModel
from app.models.chat_message import ChatMessageModel
from app.core.config import settings
from app.ml.trend_analyzer import TrendAnalyzer


class WaterChatbotTools:
    """Provides structured data query tools to the AI Chatbot agent."""

    @staticmethod
    def get_current_water_status(db: Session) -> Dict[str, Any]:
        """Fetches the latest reading from the database."""
        latest = (
            db.query(WaterReadingModel)
            .order_by(WaterReadingModel.timestamp.desc())
            .first()
        )
        if not latest:
            return {"status": "NO_DATA", "message": "No sensor readings recorded yet."}

        return {
            "timestamp": latest.timestamp.isoformat(),
            "ph": latest.ph,
            "turbidity_ntu": latest.turbidity,
            "tds_ppm": latest.tds,  # strictly null if uninstalled
            "ph_calibrated": latest.ph_calibrated,
            "turbidity_calibrated": latest.turbidity_calibrated,
            "tds_calibrated": latest.tds_calibrated,
            "alert_severity": latest.alert_severity,
            "alert_message": latest.alert_messages,
            "health_summary": latest.sensor_health_summary,
            "health_code": f"0x{latest.health_code:04X}",
            "is_valid": latest.is_valid,
            "is_stale": latest.is_stale,
            "data_source": latest.data_source,
            "operating_mode": latest.operating_mode,
            "ph_voltage": latest.ph_voltage,
            "turbidity_voltage": latest.turbidity_voltage,
        }

    @staticmethod
    def get_historical_metrics(db: Session, hours: int = 24) -> Dict[str, Any]:
        """Calculates 24-hour summary statistics from SQLite."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        count = (
            db.query(func.count(WaterReadingModel.id))
            .filter(WaterReadingModel.timestamp >= cutoff)
            .scalar() or 0
        )

        if count == 0:
            return {"count": 0, "status": "NO_RECENT_DATA"}

        stats = (
            db.query(
                func.avg(WaterReadingModel.ph),
                func.min(WaterReadingModel.ph),
                func.max(WaterReadingModel.ph),
                func.avg(WaterReadingModel.turbidity),
                func.max(WaterReadingModel.turbidity),
            )
            .filter(WaterReadingModel.timestamp >= cutoff, WaterReadingModel.is_valid == True)
            .first()
        )

        return {
            "timeframe_hours": hours,
            "total_samples": count,
            "ph_average": round(stats[0], 2) if stats and stats[0] is not None else None,
            "ph_min": round(stats[1], 2) if stats and stats[1] is not None else None,
            "ph_max": round(stats[2], 2) if stats and stats[2] is not None else None,
            "turbidity_average": round(stats[3], 2) if stats and stats[3] is not None else None,
            "turbidity_max": round(stats[4], 2) if stats and stats[4] is not None else None,
        }

    @staticmethod
    def get_recent_alerts(db: Session, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieves recent water quality alerts."""
        alerts = (
            db.query(AlertLogModel)
            .order_by(AlertLogModel.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "timestamp": a.timestamp.isoformat(),
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "resolved": a.resolved,
            }
            for a in alerts
        ]

    @staticmethod
    def explain_parameter_standards(parameter: str) -> Dict[str, Any]:
        """Explains safe water thresholds based on EPA and WHO standards."""
        param = parameter.lower().strip()
        if "ph" in param:
            return {
                "parameter": "pH",
                "safe_range": f"{settings.THRESHOLD_PH_MIN} to {settings.THRESHOLD_PH_MAX}",
                "unit": "pH scale (0-14)",
                "standards": "EPA National Secondary Drinking Water Regulations (6.5 to 8.5)",
                "health_implications": (
                    "Water with a low pH (<6.5) is acidic, soft, and corrosive, which can leach toxic "
                    "metal ions (lead, copper) from residential apartment plumbing fixtures. "
                    "Water with high pH (>8.5) is alkaline, producing bitter taste and mineral scale incrustation."
                ),
            }
        elif "turb" in param or "cloud" in param:
            return {
                "parameter": "Turbidity",
                "safe_limit": f"Below {settings.THRESHOLD_TURBIDITY_NTU_MAX} NTU",
                "unit": "Nephelometric Turbidity Units (NTU)",
                "standards": "WHO Drinking Water Guidelines (<5.0 NTU; ideally <1.0 NTU)",
                "health_implications": (
                    "Turbidity measures cloudiness caused by suspended colloids, clay, silt, or rust. "
                    "While not a direct toxin, high turbidity shields pathogenic microorganisms from UV/chlorine "
                    "disinfection and promotes bacterial regrowth in building storage tanks."
                ),
            }
        elif "tds" in param:
            return {
                "parameter": "Total Dissolved Solids (TDS)",
                "safe_limit": f"Below {settings.THRESHOLD_TDS_PPM_MAX} ppm",
                "unit": "parts per million (ppm) / mg/L",
                "standards": "EPA Secondary Standards (<500 ppm)",
                "health_implications": (
                    "Measures combined inorganic salts (calcium, magnesium, chlorides, sulfates). "
                    "In this Phase 1/Phase 2 monitor, the TDS sensor is reserved for future hardware installation."
                ),
            }
        else:
            return {
                "error": f"Unknown parameter '{parameter}'. Supported parameters: pH, Turbidity, TDS."
            }

    @staticmethod
    def get_recent_conversation_history(db: Session, session_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """Retrieves the recent conversation messages for the current session."""
        try:
            messages = (
                db.query(ChatMessageModel)
                .filter(ChatMessageModel.session_id == session_id)
                .order_by(ChatMessageModel.timestamp.desc())
                .limit(limit)
                .all()
            )
            # Return in chronological order
            return [
                {"role": m.role, "content": m.content}
                for m in reversed(messages)
            ]
        except Exception:
            return []
