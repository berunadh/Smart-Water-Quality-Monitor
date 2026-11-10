"""Mode-aware alert logging and notification evaluation service."""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.alert_log import AlertLogModel
from app.models.water_reading import WaterReadingModel
from app.schemas.alert import AlertSummaryResponse, AlertResponse
from app.services.mode_service import ModeService


class AlertService:
    @staticmethod
    def evaluate_and_record_alerts(db: Session, reading: WaterReadingModel) -> Optional[AlertLogModel]:
        """
        Analyzes a water reading under the active mode thresholds (Drinking vs Regular Usage)
        and logs an incident identifying EVERY violated calibrated parameter.
        Never records threshold alerts for uncalibrated sensors.
        """
        config = ModeService.get_or_create_config(db)
        eval_res = ModeService.evaluate_reading(reading, config)

        if not reading.is_valid:
            severity = 3
            title = "DATA INTEGRITY / ELECTRICAL ALARM"
            msg = reading.validation_notes or "Electrical safety violation or sensor fault."
        elif eval_res.violated_parameters:
            severity = eval_res.alert_severity or 1
            mode_tag = "DRINKING MODE" if eval_res.active_mode == "drinking" else "REGULAR USAGE"
            violated_names = [
                name
                for name, p in eval_res.parameter_evaluations.items()
                if p.status == "exceeded"
            ]
            param_summary = " + ".join(n.upper() for n in violated_names)
            title = f"{param_summary} EXCEEDED ({mode_tag})"
            msg = "; ".join(eval_res.violated_parameters)
        elif eval_res.overall_status == "SENSOR_FAULT":
            severity = 3
            title = "HARDWARE SENSOR FAULT"
            msg = reading.alert_messages or "Sensor disconnected or faulty."
        else:
            return None

        alert = AlertLogModel(
            timestamp=reading.timestamp or datetime.utcnow(),
            severity=severity,
            title=title,
            message=msg,
            resolved=False,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def get_alert_summary(db: Session) -> AlertSummaryResponse:
        all_recent = (
            db.query(AlertLogModel)
            .order_by(AlertLogModel.timestamp.desc())
            .limit(20)
            .all()
        )
        active_alerts = [a for a in all_recent if not a.resolved]

        crit_count = sum(1 for a in active_alerts if a.severity == 2)
        warn_count = sum(1 for a in active_alerts if a.severity == 1)
        fault_count = sum(1 for a in active_alerts if a.severity == 3)

        return AlertSummaryResponse(
            total_active=len(active_alerts),
            critical_count=crit_count,
            warning_count=warn_count,
            fault_count=fault_count,
            recent_alerts=[AlertResponse.model_validate(a) for a in all_recent[:15]],
        )
