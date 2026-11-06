"""ThingSpeak cloud telemetry ingestion and synchronization service."""

import httpx
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.water_reading import WaterReadingModel
from app.schemas.thingspeak import ThingSpeakFeedResponse, ThingSpeakFeedItem, ThingSpeakSyncResult
from app.services.validation_service import ValidationService


class ThingSpeakService:
    BASE_URL = "https://api.thingspeak.com"

    @classmethod
    async def fetch_feeds(
        cls,
        channel_id: str,
        read_api_key: Optional[str] = None,
        results: int = 50,
    ) -> Optional[ThingSpeakFeedResponse]:
        """Fetches recent feed entries from the ThingSpeak REST API."""
        url = f"{cls.BASE_URL}/channels/{channel_id}/feeds.json"
        params = {"results": min(results, 8000)}
        if read_api_key:
            params["api_key"] = read_api_key

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return ThingSpeakFeedResponse.model_validate(data)
                else:
                    logger.error(f"[ThingSpeak] Failed fetch: HTTP {response.status_code} - {response.text}")
                    return None
        except Exception as exc:
            logger.error(f"[ThingSpeak] Network error fetching feeds: {exc}")
            return None

    @classmethod
    def process_and_save_feeds(
        cls,
        db: Session,
        feed_items: List[ThingSpeakFeedItem],
    ) -> ThingSpeakSyncResult:
        """
        Parses raw ThingSpeak feeds, enforces data contracts, validates electrical
        invariants, and commits new non-duplicate records to the database.
        """
        new_count = 0
        failure_count = 0
        latest_id = None

        for item in feed_items:
            # Check for duplicate entry_id
            existing = db.query(WaterReadingModel).filter(WaterReadingModel.entry_id == item.entry_id).first()
            if existing:
                continue

            ph = ValidationService.parse_float_field(item.field1)
            turbidity = ValidationService.parse_float_field(item.field2)
            tds = ValidationService.parse_float_field(item.field3)
            severity = ValidationService.parse_int_field(item.field4, default=0)
            ph_v = ValidationService.parse_float_field(item.field5) or 0.0
            turb_v = ValidationService.parse_float_field(item.field6) or 0.0
            health = ValidationService.parse_int_field(item.field7, default=0)

            is_valid, notes = ValidationService.validate_reading(
                ph=ph,
                turbidity=turbidity,
                tds=tds,
                ph_board_v=ph_v,
                turbidity_board_v=turb_v,
                health_code=health,
            )

            if not is_valid:
                failure_count += 1

            record = WaterReadingModel(
                entry_id=item.entry_id,
                timestamp=item.created_at,
                ph=ph,
                turbidity=turbidity,
                tds=tds,
                alert_severity=severity,
                ph_board_voltage=ph_v,
                turbidity_board_voltage=turb_v,
                health_code=health,
                is_valid=is_valid,
                validation_notes=notes,
            )
            db.add(record)
            new_count += 1
            latest_id = item.entry_id

        if new_count > 0:
            db.commit()
            logger.info(f"[ThingSpeak] Saved {new_count} new records to database (Failures: {failure_count}).")

        return ThingSpeakSyncResult(
            channel_id=settings.THINGSPEAK_CHANNEL_ID,
            total_fetched=len(feed_items),
            new_records_saved=new_count,
            validation_failures=failure_count,
            latest_entry_id=latest_id,
        )
