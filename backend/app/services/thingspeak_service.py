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
from app.services.mode_service import ModeService


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
        field_profile: Optional[str] = None,
    ) -> ThingSpeakSyncResult:
        """
        Parses raw ThingSpeak feeds, enforces data contracts, validates electrical
        invariants, and commits new non-duplicate records to the database.
        Supports default '8field' (Channel 3570138) and optional '5field' documented mapping.
        """
        new_count = 0
        failure_count = 0
        latest_id = None
        mode_config = ModeService.get_or_create_config(db)
        profile = (field_profile or getattr(settings, "THINGSPEAK_FIELD_PROFILE", "8field")).lower()

        for item in feed_items:
            # Prevent duplicate entries via entry_id
            existing = db.query(WaterReadingModel).filter(WaterReadingModel.entry_id == item.entry_id).first()
            if existing:
                continue

            if profile == "5field":
                # Documented 5-field design mapping:
                # field1=TDS ppm, field2=pH, field3=Turbidity NTU, field4=Custom WQS, field5=System status code
                tds = ValidationService.parse_float_field(item.field1)
                ph = ValidationService.parse_float_field(item.field2)
                turbidity = ValidationService.parse_float_field(item.field3)
                status_code = ValidationService.parse_int_field(item.field5, default=-1)
                severity = 2 if status_code == 0 else (3 if status_code == -1 else (1 if status_code in (1, 2) else 0))
                ph_v = 0.0
                turb_v = 0.0
                health = (1 << 2) if status_code == -1 else 0
                tds_v = None
            else:
                # Default 8-field project mapping (Channel ID 3570138)
                ph = ValidationService.parse_float_field(item.field1)
                turbidity = ValidationService.parse_float_field(item.field2)
                tds = ValidationService.parse_float_field(item.field3)
                severity = ValidationService.parse_int_field(item.field4, default=0)
                ph_v = ValidationService.parse_float_field(item.field5) or 0.0
                turb_v = ValidationService.parse_float_field(item.field6) or 0.0
                health = ValidationService.parse_int_field(item.field7, default=0)
                tds_v = ValidationService.parse_float_field(item.field8)

            # Calibration vs Provisional flags:
            # Bits 11/12/13 indicate provisional estimates/models without experimental NVS confirmation.
            ph_prov = bool(health & (1 << 12))
            turb_prov = bool(health & (1 << 13))
            tds_prov = bool(health & (1 << 11))
            ph_cal = (ph is not None) and (not ph_prov)
            turb_cal = (turbidity is not None) and (not turb_prov)
            tds_cal = (tds is not None) and (not tds_prov)
            item_ts = ValidationService.to_naive_utc(item.created_at) or datetime.utcnow()

            is_valid, is_stale, notes = ValidationService.validate_reading(
                ph=ph,
                turbidity=turbidity,
                tds=tds,
                ph_board_v=ph_v,
                turbidity_board_v=turb_v,
                health_code=health,
                timestamp=item_ts,
                tds_voltage=tds_v,
            )

            if not is_valid:
                failure_count += 1

            record = WaterReadingModel(
                entry_id=item.entry_id,
                device_id=settings.DEVICE_ID,
                timestamp=item_ts,
                ph=ph,
                turbidity=turbidity,
                tds=tds,  # STRICT: Remains None if omitted/uncalibrated
                ph_voltage=ph_v,
                turbidity_voltage=turb_v,
                tds_voltage=tds_v,
                ph_calibrated=ph_cal,
                turbidity_calibrated=turb_cal,
                tds_calibrated=tds_cal,
                alert_severity=severity,
                health_code=health,
                sensor_health_summary="OPERATIONAL",
                alert_messages="WATER SYSTEM NORMAL",
                data_source="thingspeak",
                operating_mode="real",
                water_quality_mode=mode_config.active_mode,
                is_valid=is_valid,
                is_stale=is_stale,
                validation_notes=notes,
            )

            # Evaluate against active water quality mode thresholds cleanly
            evaluation = ModeService.evaluate_reading(record, mode_config)
            if not is_valid:
                record.alert_severity = 3
                record.sensor_health_summary = "ELECTRICAL HAZARD"
                record.alert_messages = notes or "ELECTRICAL SAFETY ALARM"
            elif evaluation.violated_parameters:
                record.alert_severity = evaluation.alert_severity
                record.sensor_health_summary = "CRITICAL" if evaluation.alert_severity >= 2 else "WARNING"
                record.alert_messages = "; ".join(evaluation.violated_parameters)
            elif severity >= 3 or evaluation.overall_status == "SENSOR_FAULT":
                record.alert_severity = 3
                record.sensor_health_summary = "SENSOR FAULT"
                record.alert_messages = "HARDWARE FAULT / PROBE DISCONNECTED"
            elif evaluation.overall_status == "CALIBRATION_PENDING":
                record.alert_severity = 0
                record.sensor_health_summary = "CALIBRATION PENDING"
                record.alert_messages = "CALIBRATION PENDING"
            else:
                record.alert_severity = 0
                record.sensor_health_summary = "OPERATIONAL"
                record.alert_messages = "WATER SYSTEM NORMAL"

            db.add(record)
            new_count += 1
            latest_id = item.entry_id

            # Add to Alert Log ONLY for threshold breaches or electrical/sensor faults (never calibration pending)
            if record.alert_severity > 0:
                alert_log = AlertLogModel(
                    timestamp=item_ts,
                    severity=record.alert_severity,
                    title=f"{evaluation.mode_label.upper()} ALERT" if evaluation.violated_parameters else record.sensor_health_summary,
                    message=record.alert_messages,
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

    @classmethod
    async def sync_latest_to_db(cls, db: Session, results: int = 50) -> Optional[ThingSpeakSyncResult]:
        """Convenience async helper to fetch recent ThingSpeak feeds and persist new entries."""
        channel_id = str(settings.THINGSPEAK_CHANNEL_ID)
        if not channel_id or channel_id in ("0", "YOUR_CHANNEL_ID"):
            return None
        feed_response = await cls.fetch_feeds(
            channel_id=channel_id,
            read_api_key=settings.THINGSPEAK_READ_API_KEY,
            results=results,
        )
        if not feed_response:
            return None
        return cls.process_and_save_feeds(db, feed_response.feeds)
