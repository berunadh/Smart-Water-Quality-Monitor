"""Demo and simulation service for realistic offline water telemetry generation."""

import random
import math
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.water_reading import WaterReadingModel
from app.models.alert_log import AlertLogModel
from app.core.logging import logger


class DemoService:
    """
    Generates realistic, explicitly-labelled simulated sensor streams for development,
    automated testing, ML benchmarking, and frontend demonstrations when physical ESP32
    hardware is disconnected.
    """

    @classmethod
    def generate_demo_reading(
        cls,
        scenario: str = "normal",
        timestamp: Optional[datetime] = None,
        sequence_step: int = 0,
    ) -> WaterReadingModel:
        """
        Synthesizes a single water reading adhering strictly to physical models.
        TDS is STRICTLY None / null.
        """
        now = timestamp or datetime.utcnow()
        device_id = settings.DEVICE_ID

        # Baseline Municipal Tap Water Constants
        base_ph = 7.35
        base_turb = 0.85
        ph_cal = True
        turb_cal = True
        tds_cal = False  # TDS absent

        if scenario == "normal":
            # Natural micro-fluctuation (diurnal sine wave + Gaussian jitter)
            diurnal_ph = 0.08 * math.sin(sequence_step * 0.1)
            ph = round(base_ph + diurnal_ph + random.uniform(-0.04, 0.04), 2)
            turbidity = round(base_turb + (0.15 * math.cos(sequence_step * 0.1)) + random.uniform(-0.05, 0.08), 2)
            if turbidity < 0.1:
                turbidity = 0.1
            severity = 0
            alert_msg = "WATER SYSTEM NORMAL"
            health_code = 0x0020  # Bit 5: TDS unavailable
            health_summary = "OPERATIONAL"
            is_valid = True
            is_stale = False
            ph_v = round(2.50 + (ph - 7.00) * 0.18, 3)
            turb_v = round(4.25 - (turbidity * 0.08), 3)
            notes = "SIMULATED NORMAL"

        elif scenario == "warning":
            # Elevated turbidity (e.g. minor municipal pipe flushing)
            ph = round(7.40 + random.uniform(-0.05, 0.05), 2)
            turbidity = round(6.8 + random.uniform(-0.4, 0.6), 2)
            severity = 1
            alert_msg = "ELEVATED TURBIDITY (>5 NTU)"
            health_code = 0x0020
            health_summary = "WARNING (TURBIDITY)"
            is_valid = True
            is_stale = False
            ph_v = round(2.50 + (ph - 7.00) * 0.18, 3)
            turb_v = round(3.40 + random.uniform(-0.05, 0.05), 3)
            notes = "SIMULATED WARNING (TURBIDITY)"

        elif scenario == "critical":
            # Dangerous acid intrusion or chemical imbalance
            ph = round(5.15 + random.uniform(-0.1, 0.1), 2)
            turbidity = round(28.5 + random.uniform(-1.5, 2.5), 2)
            severity = 2
            alert_msg = "CRITICAL: ACIDIC pH & HIGH TURBIDITY"
            health_code = 0x0020
            health_summary = "CRITICAL WATER QUALITY"
            is_valid = True
            is_stale = False
            ph_v = round(1.85 + random.uniform(-0.03, 0.03), 3)
            turb_v = round(1.50 + random.uniform(-0.05, 0.05), 3)
            notes = "SIMULATED CRITICAL BREACH"

        elif scenario == "sensor_fault":
            # Hardware fault / ADC over-range hazard
            ph = None  # Invalidated
            turbidity = None
            ph_cal = False
            turb_cal = False
            severity = 3
            alert_msg = "ADC OVER-RANGE (>3.05V)"
            health_code = 0x0034  # Bit 2 (pH fault) + Bit 4 (Over-range) + Bit 5 (TDS)
            health_summary = "ELECTRICAL HAZARD"
            is_valid = False
            is_stale = False
            ph_v = 7.835  # Simulates un-attenuated voltage passing to ADC
            turb_v = 4.10
            notes = "SIMULATED ELECTRICAL OVER-RANGE"

        elif scenario == "stale":
            # Stale data scenario: normal reading but timestamp is 45 minutes in the past
            now = now - timedelta(minutes=45)
            ph = 7.30
            turbidity = 0.9
            severity = 0
            alert_msg = "STALE DATA"
            health_code = 0x0020
            health_summary = "STALE TELEMETRY"
            is_valid = True
            is_stale = True
            ph_v = 2.55
            turb_v = 4.15
            notes = "SIMULATED STALE TELEMETRY"

        else:
            raise ValueError(f"Unknown demo scenario: {scenario}")

        return WaterReadingModel(
            device_id=device_id,
            entry_id=None,  # Demo readings have no ThingSpeak entry_id
            timestamp=now,
            ph=ph,
            turbidity=turbidity,
            tds=None,  # STRICT REQUIREMENT: TDS is absent / null
            ph_voltage=ph_v,
            turbidity_voltage=turb_v,
            ph_calibrated=ph_cal,
            turbidity_calibrated=turb_cal,
            tds_calibrated=tds_cal,
            alert_severity=severity,
            health_code=health_code,
            sensor_health_summary=health_summary,
            alert_messages=alert_msg,
            data_source="simulated",
            operating_mode="demo",
            is_valid=is_valid,
            is_stale=is_stale,
            validation_notes=notes,
        )

    @classmethod
    def seed_demo_history(cls, db: Session, count: int = 60, force: bool = False) -> int:
        """
        Seeds the SQLite database with a realistic time-series of readings spanning the
        past 3 hours if no data currently exists.
        """
        existing_count = db.query(WaterReadingModel).count()
        if existing_count > 0 and not force:
            logger.info(f"[DemoService] Database already contains {existing_count} records. Skipping seed.")
            return existing_count

        logger.info(f"[DemoService] Generating {count} simulated water telemetry records...")
        base_time = datetime.utcnow() - timedelta(minutes=count * 2)

        created = 0
        for i in range(count):
            t = base_time + timedelta(minutes=i * 2)
            # Inject an elevated turbidity event around sample 40-45
            if 40 <= i <= 44:
                scenario = "warning"
            else:
                scenario = "normal"

            reading = cls.generate_demo_reading(scenario=scenario, timestamp=t, sequence_step=i)
            db.add(reading)
            created += 1

            # Log corresponding alert for warning scenario
            if reading.alert_severity > 0:
                alert = AlertLogModel(
                    timestamp=t,
                    severity=reading.alert_severity,
                    title="SIMULATED TURBIDITY SPIKE",
                    message="Temporary particulate increase detected during distribution flush.",
                    resolved=(i == 44),
                    resolved_at=t + timedelta(minutes=10) if i == 44 else None,
                )
                db.add(alert)

        db.commit()
        logger.info(f"[DemoService] Successfully seeded {created} demo records.")
        return created
