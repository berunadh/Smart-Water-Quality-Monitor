"""Data quality, electrical safety, and staleness validation service."""

from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timezone
from app.core.config import settings


class ValidationService:
    STALENESS_THRESHOLD_SECONDS = 300  # 5 minutes

    @staticmethod
    def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
        """Normalizes aware or naive datetimes to naive UTC to avoid tz arithmetic TypeError."""
        if dt is None:
            return None
        if dt.tzinfo is not None and dt.utcoffset() is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @staticmethod
    def validate_reading(
        ph: Optional[float],
        turbidity: Optional[float],
        tds: Optional[float],
        ph_board_v: float,
        turbidity_board_v: float,
        health_code: int,
        timestamp: Optional[datetime] = None,
        tds_voltage: Optional[float] = None,
    ) -> Tuple[bool, bool, Optional[str]]:
        """
        Validates electrical plausibility, physical bounds, staleness, and missing sensor integrity.
        Note: pH & Turbidity use 15k/10k voltage dividers (0.40x), while TDS uses direct 3.3V ADC (1.0x).
        Returns: (is_valid: bool, is_stale: bool, validation_notes: Optional[str])
        """
        notes = []
        is_stale = False

        # 1. Staleness check (UTC-normalized)
        ts_utc = ValidationService.to_naive_utc(timestamp)
        if ts_utc:
            age_seconds = (datetime.utcnow() - ts_utc).total_seconds()
            if age_seconds > ValidationService.STALENESS_THRESHOLD_SECONDS:
                is_stale = True
                notes.append(f"STALE: Reading is {int(age_seconds / 60)} minutes old")

        # 2. Electrical Invariant Verification (ADC limit safety)
        # pH & Turbidity ADC pin voltage is V_board * 0.40; TDS has NO divider (V_ADC directly)
        ph_adc_est = ph_board_v * settings.VOLTAGE_DIVIDER_RATIO
        turb_adc_est = turbidity_board_v * settings.VOLTAGE_DIVIDER_RATIO

        if ph_adc_est >= settings.ADC_SAFE_VOLTAGE_MAX:
            return False, is_stale, f"HAZARD: pH ADC voltage ({ph_adc_est:.2f}V) exceeds 3.05V safety limit!"
        if turb_adc_est >= settings.ADC_SAFE_VOLTAGE_MAX:
            return False, is_stale, f"HAZARD: Turbidity ADC voltage ({turb_adc_est:.2f}V) exceeds 3.05V safety limit!"
        if tds_voltage is not None and tds_voltage >= settings.ADC_SAFE_VOLTAGE_MAX:
            return False, is_stale, f"HAZARD: TDS ADC voltage ({tds_voltage:.2f}V) exceeds 3.05V safety limit!"

        # 3. TDS Integrity Check (Strict Rule: Uninstalled/uncalibrated TDS must NEVER be 0.0)
        if tds == 0.0:
            notes.append("WARNING: TDS reported as 0.0. If sensor is absent or uncalibrated, value should be NULL.")
        if tds is not None and (tds < 0.0 or tds > 5000.0):
            return False, is_stale, f"PHYSICAL BOUND VIOLATION: TDS {tds} ppm outside [0, 5000]"

        # 4. pH Physical Sanity Check
        if ph is not None:
            if ph < 0.0 or ph > 14.0:
                return False, is_stale, f"PHYSICAL BOUND VIOLATION: pH {ph} outside [0.0, 14.0]"

        # 5. Turbidity Physical Sanity Check
        if turbidity is not None:
            if turbidity < 0.0 or turbidity > 3000.0:
                return False, is_stale, f"PHYSICAL BOUND VIOLATION: Turbidity {turbidity} NTU outside [0, 3000]"

        # 6. Check Health Code Bitmask for Electrical Alarm
        if health_code & (1 << 4):  # HEALTH_ADC_OVER_RANGE
            return False, is_stale, "HARDWARE FAULT: Firmware flagged ADC over-range in health bitmask."

        validation_summary = "; ".join(notes) if notes else "VALID"
        return True, is_stale, validation_summary

    @classmethod
    def parse_float_field(cls, value: Optional[str]) -> Optional[float]:
        """Safely parses a string field from ThingSpeak; returns None if empty or invalid."""
        if value is None:
            return None
        v = str(value).strip()
        if not v or v.lower() in ("null", "nan", "none", "n/a", ""):
            return None
        try:
            return float(v)
        except ValueError:
            return None

    @classmethod
    def parse_int_field(cls, value: Optional[str], default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(str(value).strip())
        except ValueError:
            return default
