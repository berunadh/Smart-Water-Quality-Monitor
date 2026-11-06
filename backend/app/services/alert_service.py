"""Alert logging and notification evaluation service."""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert_log import AlertLogModel
from app.models.water_reading import WaterReadingModel
from app.schemas.alert import AlertSummaryResponse, AlertResponse


class AlertService:
    @staticmethod
    def evaluate_and_record_alerts(db: Session, reading: WaterReadingModel) -> Optional[AlertLogModel]:
        """
        Analyzes a fresh water reading and writes an alert log if any safety threshold is breached.
        """
        severity = reading.alert_severity
        if severity == 0 and reading.is_valid:
            # Everything is normal
            return None

        title = "WATER QUALITY ALERT"
        msg = "Water parameters outside acceptable range."

        if not reading.is_valid:
            severity = 3
            title = "DATA INTEGRITY / ELECTRICAL ALARM"
            msg = reading.validation_notes or "Electrical safety violation or sensor fault."
        elif reading.turbidity is not None and reading.turbidity >= settings.THRESHOLD_TURBIDITY_NTU_MAX:
            title = "HIGH TURBIDITY WARNING"
            msg = f"Turbidity reached {reading.turbidity:.1f} NTU (Safe limit: {settings.THRESHOLD_TURBIDITY_NTU_MAX} NTU)."
        elif reading.ph is not None and (reading.ph < settings.THRESHOLD_PH_MIN or reading.ph > settings.THRESHOLD_PH_MAX):
            title = "pH LEVEL OUT OF RANGE"
            msg = f"pH level reached {reading.ph:.2f} (Acceptable: {settings.THRESHOLD_PH_MIN} - {settings.THRESHOLD_PH_MAX})."

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
        active_alerts = (
            db.query(AlertLogModel)
            .filter(AlertLogModel.resolved == False)
            .order_by(AlertLogModel.timestamp.desc())
            .all()
        )

        crit_count = sum(1 for a in active_alerts if a.severity == 2)
        warn_count = sum(1 for a in active_alerts if a.severity == 1)
        fault_count = sum(1 for a in active_alerts if a.severity == 3)

        return AlertSummaryResponse(
            total_active=len(active_alerts),
            critical_count=crit_count,
            warning_count=warn_count,
            fault_count=fault_count,
            recent_alerts=[AlertResponse.model_validate(a) for a in active_alerts[:10]],
        )
