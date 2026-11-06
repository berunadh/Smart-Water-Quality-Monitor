"""Alerts and notification management endpoints."""

from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.alert_log import AlertLogModel
from app.schemas.alert import AlertResponse, AlertSummaryResponse
from app.services.alert_service import AlertService

router = APIRouter()


@router.get("/summary", response_model=AlertSummaryResponse)
def get_alert_summary(db: Session = Depends(get_db)):
    """Retrieves counts and details of active unresolved alerts."""
    return AlertService.get_alert_summary(db)


@router.get("/history", response_model=List[AlertResponse])
def get_alert_history(
    limit: int = Query(50, ge=1, le=500),
    resolved: bool = Query(None),
    db: Session = Depends(get_db),
):
    """Retrieves historical alert events."""
    query = db.query(AlertLogModel)
    if resolved is not None:
        query = query.filter(AlertLogModel.resolved == resolved)

    return query.order_by(AlertLogModel.timestamp.desc()).limit(limit).all()


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Marks an alert event as acknowledged and resolved."""
    alert = db.query(AlertLogModel).filter(AlertLogModel.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert record not found")

    alert.resolved = True
    alert.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert
