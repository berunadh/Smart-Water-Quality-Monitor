"""Demo and simulation service for realistic offline water telemetry generation."""

import random
import math
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.water_reading import WaterReadingModel
from app.models.water_quality_config import WaterQualityConfigModel
from app.models.alert_log import AlertLogModel
from app.services.mode_service import ModeService
from app.core.logging import logger


class DemoService:
    """
    Generates realistic, explicitly-labelled simulated sensor streams for development,
    automated testing, ML benchmarking, and frontend demonstrations when physical ESP32
    hardware is not streaming live.
    """

    @classmethod
    def generate_demo_reading(
        cls,
        scenario: str = "normal",
        timestamp: Optional[datetime] = None,
        sequence_step: int = 0,
        config: Optional[WaterQualityConfigModel] = None,
    ) -> WaterReadingModel:
        """
        Synthesizes a single multi-sensor telemetry record adhering strictly to hardware specs:
        - pH (GPIO34, 15k/10k divider -> V_board)
        - Turbidity (GPIO32, 15k/10k divider -> V_board)
        - TDS (GPIO35, direct 3.3V ADC -> V_adc, no divider)
        """
        now = timestamp or datetime.utcnow()
        device_id = settings.DEVICE_ID
        active_mode = config.active_mode if config else "drinking"

        base_ph = 7.28
        base_turb = 0.55  # Safely within BIS IS 10500:2012 (<= 1.0 NTU)
        base_tds = 220.0  # Safely within BIS IS 10500:2012 (<= 500 mg/L)
        ph_cal = True
        turb_cal = True
        tds_cal = True

        if scenario == "normal":
            diurnal_ph = 0.08 * math.sin(sequence_step * 0.1)
            ph = round(base_ph + diurnal_ph + random.uniform(-0.04, 0.04), 2)
            turbidity = round(base_turb + (0.10 * math.cos(sequence_step * 0.1)) + random.uniform(-0.04, 0.06), 2)
            if turbidity < 0.1:
                turbidity = 0.1
            tds = round(base_tds + (15.0 * math.sin(sequence_step * 0.08)) + random.uniform(-5.0, 5.0), 1)
            severity = 0
            alert_msg = "WATER SYSTEM NORMAL"
            health_code = 0x0000
            if active_mode == "regular_usage":
                health_code |= (1 << 9)
            health_summary = "OPERATIONAL"
            is_valid = True
            is_stale = False
            ph_v = round(2.50 + (ph - 7.00) * 0.18, 3)
            turb_v = round(4.25 - (turbidity * 0.08), 3)
            tds_v = round(0.75 + (tds / 1000.0) * 0.85, 3)
            notes = "SIMULATED NORMAL"

        elif scenario == "warning":
            # Drift: Turbidity ~2.8 NTU & TDS ~620 mg/L
            # Triggers alert in Drinking Mode (<=1 NTU, <=500 ppm), acceptable in Regular Usage Mode (<=10 NTU, <=1000 ppm)
            ph = round(7.40 + random.uniform(-0.05, 0.05), 2)
            turbidity = round(2.85 + random.uniform(-0.25, 0.35), 2)
            tds = round(620.0 + random.uniform(-15.0, 20.0), 1)
            severity = 1
            alert_msg = "TURBIDITY & TDS ELEVATED"
            health_code = 0x0000
            if active_mode == "regular_usage":
                health_code |= (1 << 9)
            health_summary = "WARNING (TURBIDITY/TDS)"
            is_valid = True
            is_stale = False
            ph_v = round(2.50 + (ph - 7.00) * 0.18, 3)
            turb_v = round(3.60 + random.uniform(-0.05, 0.05), 3)
            tds_v = round(1.52 + random.uniform(-0.03, 0.03), 3)
            notes = "SIMULATED WARNING (DRIFT)"

        elif scenario == "critical":
            # Severe acid excursion + turbidity + high TDS (exceeds both Drinking and Regular Usage modes)
            ph = round(5.15 + random.uniform(-0.1, 0.1), 2)
            turbidity = round(18.5 + random.uniform(-1.5, 2.5), 2)
            tds = round(1350.0 + random.uniform(-25.0, 35.0), 1)
            severity = 2
            alert_msg = "CRITICAL: pH, TURBIDITY & TDS EXCEEDED"
            health_code = 0x0000
            if active_mode == "regular_usage":
                health_code |= (1 << 9)
            health_summary = "CRITICAL WATER QUALITY"
            is_valid = True
            is_stale = False
            ph_v = round(1.85 + random.uniform(-0.03, 0.03), 3)
            turb_v = round(1.50 + random.uniform(-0.05, 0.05), 3)
            tds_v = round(2.38 + random.uniform(-0.04, 0.04), 3)
            notes = "SIMULATED CRITICAL BREACH"

        elif scenario == "uncalibrated":
            # Models physical hardware before reference calibration is performed
            ph = None
            turbidity = None
            tds = None
            ph_cal = False
            turb_cal = False
            tds_cal = False
            severity = 0
            alert_msg = "CALIBRATION PENDING"
            health_code = 0x0040  # Bit 6: CALIBRATION_PENDING
            if active_mode == "regular_usage":
                health_code |= (1 << 9)
            health_summary = "CALIBRATION PENDING"
            is_valid = True
            is_stale = False
            ph_v = 4.742   # 1.897V ADC * 2.5
            turb_v = 1.465 # 0.586V ADC * 2.5
            tds_v = 1.876  # Direct 1.0x ADC
            notes = "SIMULATED UNCALIBRATED SENSORS (RAW VOLTAGES ONLY)"

        elif scenario == "sensor_fault":
            ph = None
            turbidity = None
            tds = None
            ph_cal = False
            turb_cal = False
            tds_cal = False
            severity = 3
            alert_msg = "ADC OVER-RANGE (>3.05V)"
            health_code = 0x0134  # Bit 2 (pH) + Bit 4 (Over-range) + Bit 5 (TDS unavail) + Bit 8 (TDS fault)
            health_summary = "ELECTRICAL HAZARD"
            is_valid = False
            is_stale = False
            ph_v = 7.835
            turb_v = 4.10
            tds_v = 0.0
            notes = "SIMULATED ELECTRICAL OVER-RANGE"

        elif scenario == "stale":
            now = now - timedelta(minutes=45)
            ph = 7.25
            turbidity = 0.60
            tds = 210.0
            severity = 0
            alert_msg = "STALE DATA"
            health_code = 0x0000
            if active_mode == "regular_usage":
                health_code |= (1 << 9)
            health_summary = "STALE TELEMETRY"
            is_valid = True
            is_stale = True
            ph_v = 2.55
            turb_v = 4.18
            tds_v = 1.10
            notes = "SIMULATED STALE TELEMETRY"

        else:
            raise ValueError(f"Unknown demo scenario: {scenario}")

        reading = WaterReadingModel(
            device_id=device_id,
            entry_id=None,
            timestamp=now,
            ph=ph,
            turbidity=turbidity,
            tds=tds,
            ph_voltage=ph_v,
            turbidity_voltage=turb_v,
            tds_voltage=tds_v,
            ph_calibrated=ph_cal,
            turbidity_calibrated=turb_cal,
            tds_calibrated=tds_cal,
            alert_severity=severity,
            health_code=health_code,
            sensor_health_summary=health_summary,
            alert_messages=alert_msg,
            data_source="simulated",
            operating_mode="demo",
            water_quality_mode=active_mode,
            is_valid=is_valid,
            is_stale=is_stale,
            validation_notes=notes,
        )

        # Evaluate dynamically against active mode config if supplied
        if config is not None and is_valid and scenario not in ("uncalibrated", "stale"):
            eval_res = ModeService.evaluate_reading(reading, config)
            reading.alert_severity = eval_res.alert_severity
            if eval_res.violated_parameters:
                reading.alert_messages = "; ".join(eval_res.violated_parameters)
                reading.sensor_health_summary = "CRITICAL" if eval_res.alert_severity >= 2 else "WARNING"
            else:
                reading.alert_messages = "WATER SYSTEM NORMAL"
                reading.sensor_health_summary = "OPERATIONAL"

        return reading

    @classmethod
    def seed_demo_history(cls, db: Session, count: int = 60, force: bool = False) -> int:
        """
        Seeds the SQLite database with a realistic time-series of readings spanning the
        past 2 hours if no data currently exists.
        """
        existing_count = db.query(WaterReadingModel).count()
        if existing_count > 0 and not force:
            logger.info(f"[DemoService] Database already contains {existing_count} records. Skipping seed.")
            return existing_count

        logger.info(f"[DemoService] Generating {count} simulated multi-sensor telemetry records...")
        config = ModeService.get_or_create_config(db)
        base_time = datetime.utcnow() - timedelta(minutes=count * 2)

        created = 0
        for i in range(count):
            t = base_time + timedelta(minutes=i * 2)
            if 40 <= i <= 44:
                scenario = "warning"
            else:
                scenario = "normal"

            reading = cls.generate_demo_reading(scenario=scenario, timestamp=t, sequence_step=i, config=config)
            db.add(reading)
            created += 1

            if reading.alert_severity > 0:
                alert = AlertLogModel(
                    timestamp=t,
                    severity=reading.alert_severity,
                    title="SIMULATED TURBIDITY & TDS SPIKE",
                    message=reading.alert_messages,
                    resolved=(i == 44),
                    resolved_at=t + timedelta(minutes=10) if i == 44 else None,
                )
                db.add(alert)

        db.commit()
        logger.info(f"[DemoService] Successfully seeded {created} demo water telemetry records.")
        return created
