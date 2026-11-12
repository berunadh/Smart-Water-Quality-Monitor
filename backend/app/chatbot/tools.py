"""Tool definitions for LLM context retrieval, dual-mode evaluation, and water domain reasoning."""

from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.water_reading import WaterReadingModel
from app.models.alert_log import AlertLogModel
from app.models.chat_message import ChatMessageModel
from app.services.mode_service import ModeService


class WaterChatbotTools:
    """Provides structured telemetry, threshold, trend, and conversation query tools to the AI Chatbot."""

    @staticmethod
    def get_current_water_status(db: Session) -> Dict[str, Any]:
        """Fetches latest reading alongside active Water Quality Mode evaluation & thresholds."""
        latest = ModeService.get_latest_preferred_reading(db)
        config = ModeService.get_or_create_config(db)
        profile = ModeService.build_profile(config, "drinking" if config.active_mode == "drinking" else "regular_usage")
        evaluation = ModeService.evaluate_reading(latest, config)

        base_thresholds = {
            "mode": config.active_mode,
            "mode_label": profile.label,
            "reference_note": profile.reference_note,
            "ph_min": profile.ph_min,
            "ph_max": profile.ph_max,
            "turbidity_max": profile.turbidity_max,
            "tds_max": profile.tds_max,
            "disclaimer": evaluation.preliminary_disclaimer,
        }

        if not latest:
            return {
                "status": "NO_DATA",
                "message": "No sensor readings recorded yet.",
                "active_thresholds": base_thresholds,
                "evaluation": evaluation.model_dump(),
            }

        age_seconds = (datetime.utcnow() - latest.timestamp).total_seconds()
        is_stale = latest.is_stale or (age_seconds > 300)

        return {
            "device_id": latest.device_id,
            "timestamp": latest.timestamp.isoformat(),
            "age_minutes": round(age_seconds / 60.0, 1),
            "ph": latest.ph,
            "turbidity_ntu": latest.turbidity,
            "tds_ppm": latest.tds,
            "ph_calibrated": latest.ph_calibrated,
            "turbidity_calibrated": latest.turbidity_calibrated,
            "tds_calibrated": latest.tds_calibrated,
            "ph_voltage": latest.ph_voltage,
            "turbidity_voltage": latest.turbidity_voltage,
            "tds_voltage": latest.tds_voltage,
            "alert_severity": evaluation.alert_severity,
            "alert_message": "; ".join(evaluation.violated_parameters) if evaluation.violated_parameters else latest.alert_messages,
            "violated_parameters": evaluation.violated_parameters,
            "parameter_evaluations": {k: v.model_dump() for k, v in evaluation.parameter_evaluations.items()},
            "overall_evaluation_status": evaluation.overall_status,
            "wqs": evaluation.wqs,
            "water_status_code": evaluation.water_status_code,
            "water_status_label": evaluation.water_status_label,
            "critical_hazard": evaluation.critical_hazard,
            "hazard_reasons": evaluation.hazard_reasons,
            "health_summary": latest.sensor_health_summary,
            "health_code": f"0x{latest.health_code:04X}",
            "is_valid": latest.is_valid,
            "is_stale": is_stale,
            "data_source": latest.data_source,
            "operating_mode": latest.operating_mode,
            "active_thresholds": base_thresholds,
        }

    @staticmethod
    def get_historical_metrics(db: Session, hours: int = 24) -> Dict[str, Any]:
        """Calculates timeframe summary statistics from SQLite including calibrated TDS."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        count = (
            db.query(func.count(WaterReadingModel.id))
            .filter(WaterReadingModel.timestamp >= cutoff)
            .scalar() or 0
        )

        if count == 0:
            return {"total_samples": 0, "status": "NO_RECENT_DATA"}

        stats = (
            db.query(
                func.avg(WaterReadingModel.ph),
                func.min(WaterReadingModel.ph),
                func.max(WaterReadingModel.ph),
                func.avg(WaterReadingModel.turbidity),
                func.max(WaterReadingModel.turbidity),
                func.avg(WaterReadingModel.tds),
                func.min(WaterReadingModel.tds),
                func.max(WaterReadingModel.tds),
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
            "tds_average": round(stats[5], 1) if stats and stats[5] is not None else None,
            "tds_min": round(stats[6], 1) if stats and stats[6] is not None else None,
            "tds_max": round(stats[7], 1) if stats and stats[7] is not None else None,
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
    def explain_parameter_standards(parameter: str, mode: str = "drinking") -> Dict[str, Any]:
        """Explains water quality thresholds based on BIS IS 10500:2012 (Drinking) or Regular Usage."""
        param = parameter.lower().strip()
        if "ph" in param:
            return {
                "parameter": "pH",
                "drinking_limit": "6.5 to 8.5 (BIS IS 10500:2012 Acceptable Limit)",
                "unit": "pH scale (0–14)",
                "implications": (
                    "Low pH (<6.5) is acidic and corrosive to plumbing, risking metal leaching; "
                    "high pH (>8.5) causes bitter taste and scale formation."
                ),
            }
        elif "turb" in param or "cloud" in param:
            return {
                "parameter": "Turbidity",
                "drinking_limit": "≤ 1.0 NTU (BIS IS 10500:2012 Acceptable Limit)",
                "unit": "NTU",
                "implications": (
                    "Suspended particulates scatter light and shield pathogens from disinfection."
                ),
            }
        elif "tds" in param or "dissolved" in param:
            return {
                "parameter": "Total Dissolved Solids (TDS)",
                "drinking_limit": "≤ 500 mg/L (ppm) (BIS IS 10500:2012 Acceptable Limit)",
                "unit": "mg/L (ppm)",
                "implications": (
                    "Estimates total dissolved inorganic salts via electrical conductivity on GPIO35 (direct 3.3V, ~25°C nominal with no automatic temperature compensation)."
                ),
            }
        return {"error": f"Unknown parameter '{parameter}'. Supported: pH, Turbidity, TDS."}

    @staticmethod
    def get_recent_conversation_history(db: Session, session_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """Retrieves recent conversation messages for context-aware follow-ups."""
        try:
            messages = (
                db.query(ChatMessageModel)
                .filter(ChatMessageModel.session_id == session_id)
                .order_by(ChatMessageModel.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [{"role": m.role, "content": m.content} for m in reversed(messages)]
        except Exception:
            return []
