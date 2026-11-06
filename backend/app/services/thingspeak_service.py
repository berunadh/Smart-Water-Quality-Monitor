"""ThingSpeak cloud telemetry ingestion and synchronization service."""

import httpx
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.water_reading import WaterReadingModel
from app.models.alert_log import AlertLogModel
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
        if not channel_id or channel_id == "0" or channel_id == "YOUR_CHANNEL_ID":
            logger.warning("[ThingSpeak] Unconfigured Channel ID. Cannot fetch real cloud feeds.")
            return None

        url = f"{cls.BASE_URL}/channels/{channel_id}/feeds.json"
        params = {"results": min(results, 8000)}

        # Private channels require the Read API key
        if read_api_key and read_api_key not in ("YOUR_READ_API_KEY", ""):
            params["api_key"] = read_api_key

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return ThingSpeakFeedResponse.model_validate(data)
                elif response.status_code == 404:
                    logger.error(f"[ThingSpeak] Channel {channel_id} not found (HTTP 404).")
                    return None
                elif response.status_code == 400:
                    logger.error(f"[ThingSpeak] Bad Request (HTTP 400). Check channel privacy and Read API key.")
                    return None
                else:
                    logger.error(f"[ThingSpeak] Failed fetch: HTTP {response.status_code} - {response.text}")
                    return None
        except httpx.RequestError as exc:
            logger.error(f"[ThingSpeak] Network error connecting to ThingSpeak: {exc}")
            return None
        except Exception as exc:
            logger.error(f"[ThingSpeak] Unexpected error parsing feeds: {exc}")
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
            # Prevent duplicate entries via entry_id
            existing = db.query(WaterReadingModel).filter(WaterReadingModel.entry_id == item.entry_id).first()
            if existing:
                continue

            # Parse Fields
            ph = ValidationService.parse_float_field(item.field1)
            turbidity = ValidationService.parse_float_field(item.field2)
            tds = ValidationService.parse_float_field(item.field3)
            severity = ValidationService.parse_int_field(item.field4, default=0)
            ph_v = ValidationService.parse_float_field(item.field5) or 0.0
            turb_v = ValidationService.parse_float_field(item.field6) or 0.0
            health = ValidationService.parse_int_field(item.field7, default=0)

            # Calibration flags: If field was sent, probe is calibrated; otherwise pending
            ph_cal = (ph is not None)
            turb_cal = (turbidity is not None)
            tds_cal = (tds is not None)

            # Determine alert messages & health summary
            if severity == 3:
                alert_msg = "SENSOR FAULT / HAZARD"
                health_summary = "SENSOR FAULT"
            elif severity == 2:
                alert_msg = "CRITICAL WATER QUALITY BREACH"
                health_summary = "CRITICAL"
            elif severity == 1:
                alert_msg = "WATER QUALITY WARNING"
                health_summary = "WARNING"
            else:
                alert_msg = "WATER SYSTEM NORMAL"
                health_summary = "OPERATIONAL"

            is_valid, is_stale, notes = ValidationService.validate_reading(
                ph=ph,
                turbidity=turbidity,
                tds=tds,
                ph_board_v=ph_v,
                turbidity_board_v=turb_v,
                health_code=health,
                timestamp=item.created_at,
            )

            if not is_valid:
                failure_count += 1

            record = WaterReadingModel(
                entry_id=item.entry_id,
                device_id=settings.DEVICE_ID,
                timestamp=item.created_at,
                ph=ph,
                turbidity=turbidity,
                tds=tds,  # STRICT: Remains None if omitted
                ph_voltage=ph_v,
                turbidity_voltage=turb_v,
                ph_calibrated=ph_cal,
                turbidity_calibrated=turb_cal,
                tds_calibrated=tds_cal,
                alert_severity=severity,
                health_code=health,
                sensor_health_summary=health_summary,
                alert_messages=alert_msg,
                data_source="thingspeak",
                operating_mode="real",
                is_valid=is_valid,
                is_stale=is_stale,
                validation_notes=notes,
            )
            db.add(record)
            new_count += 1
            latest_id = item.entry_id

            # Add to Alert Log if warning or critical
            if severity > 0:
                alert_log = AlertLogModel(
                    timestamp=item.created_at,
                    severity=severity,
                    title=alert_msg,
                    message=notes or "Threshold breach reported by ESP32 sensor node.",
                    resolved=False,
                )
                db.add(alert_log)

        if new_count > 0:
            db.commit()
            logger.info(f"[ThingSpeak] Saved {new_count} new records to SQLite (Validation notes/failures: {failure_count}).")

        return ThingSpeakSyncResult(
            channel_id=str(settings.THINGSPEAK_CHANNEL_ID),
            total_fetched=len(feed_items),
            new_records_saved=new_count,
            validation_failures=failure_count,
            latest_entry_id=latest_id,
        )
