"""ThingSpeak cloud integration endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.config import settings
from app.schemas.thingspeak import ThingSpeakSyncResult
from app.services.thingspeak_service import ThingSpeakService

router = APIRouter()


@router.post("/sync", response_model=ThingSpeakSyncResult)
async def sync_thingspeak_channel(
    results: int = Query(50, ge=1, le=8000),
    db: Session = Depends(get_db),
):
    """
    Manually or periodically pulls telemetry feeds from ThingSpeak,
    validates data against the ESP32 firmware contract, and saves new records.
    """
    channel_id = settings.THINGSPEAK_CHANNEL_ID
    if not channel_id or channel_id == "0":
        raise HTTPException(
            status_code=400,
            detail="ThingSpeak Channel ID is not configured. Set THINGSPEAK_CHANNEL_ID in .env",
        )

    feed_response = await ThingSpeakService.fetch_feeds(
        channel_id=channel_id,
        read_api_key=settings.THINGSPEAK_READ_API_KEY,
        results=results,
    )

    if not feed_response:
        raise HTTPException(
            status_code=502,
            detail="Unable to reach ThingSpeak API or channel returned error.",
        )

    sync_result = ThingSpeakService.process_and_save_feeds(db, feed_response.feeds)
    return sync_result
