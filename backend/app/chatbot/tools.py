"""Tool definitions for LLM function calling and agentic reasoning."""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.water_reading import WaterReadingModel
from app.models.alert_log import AlertLogModel
from app.core.config import settings


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
            "tds_ppm": latest.tds,
            "alert_severity": latest.alert_severity,
            "is_valid": latest.is_valid,
            "validation_notes": latest.validation_notes,
            "ph_board_voltage": latest.ph_board_voltage,
            "turbidity_board_voltage": latest.turbidity_board_voltage,
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
                "standards": "EPA Secondary Drinking Water Regulations / WHO Guidelines",
                "health_implications": (
                    "Low pH (<6.5) can cause pipe corrosion and heavy metal leaching. "
                    "High pH (>8.5) imparts a bitter taste and scale formation."
                ),
            }
        elif "turb" in param:
            return {
                "parameter": "Turbidity",
                "safe_limit": f"Below {settings.THRESHOLD_TURBIDITY_NTU_MAX} NTU",
                "unit": "Nephelometric Turbidity Units (NTU)",
                "standards": "WHO Drinking Water Guidelines (<5.0 NTU; ideally <1.0 NTU for disinfection)",
                "health_implications": (
                    "High turbidity indicates suspended organic/inorganic particles, rust from pipes, "
                    "or microbial contamination which can harbor pathogens and shield them from disinfection."
                ),
            }
        elif "tds" in param:
            return {
                "parameter": "Total Dissolved Solids (TDS)",
                "safe_limit": f"Below {settings.THRESHOLD_TDS_PPM_MAX} ppm",
                "unit": "parts per million (ppm) / mg/L",
                "standards": "EPA Secondary Standards (<500 ppm)",
                "health_implications": (
                    "High TDS produces hard water, mineral deposits, and altered taste. "
                    "In this system, the TDS sensor is reserved for Phase 2 hardware installation."
                ),
            }
        else:
            return {
                "error": f"Unknown parameter '{parameter}'. Supported parameters: pH, Turbidity, TDS."
            }
