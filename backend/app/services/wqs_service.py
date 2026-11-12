"""Water Quality Score (WQS) weighted sub-index and Critical Hazard Override service.

Matches firmware WaterQualityScore.h identically:
  WQS = 0.40 * q_TDS + 0.35 * q_pH + 0.25 * q_Turb

Sub-indices [0, 100] are anchored strictly on BIS 10500:2012, WHO, and
Critical Hazard Override thresholds. WQS is computed ONLY when all three
sensor readings are valid and finite; missing/invalid measurements are
never substituted with 0. Software WQS is preliminary screening only and
does NOT certify water as safe to drink.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional


WQS_WEIGHT_TDS = 0.40
WQS_WEIGHT_PH = 0.35
WQS_WEIGHT_TURB = 0.25

HAZARD_PH_MIN = 5.0
HAZARD_PH_MAX = 9.5
HAZARD_TDS_MAX_PPM = 700.0
HAZARD_TURB_MAX_NTU = 150.0
HAZARD_WQS_CAP = 20.0

WATER_STATUS_LABELS = {
    4: "Nominal",
    3: "Good",
    2: "Moderate",
    1: "Poor",
    0: "Hazard",
    -1: "Fault",
    99: "Demo",
}


def _clamp_0_100(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(100.0, value))


def compute_subindex_ph(ph: float) -> float:
    """Normalizes pH onto [0, 100] using BIS IS 10500 (6.5-8.5) & hazard bounds (5.0, 9.5)."""
    if not math.isfinite(ph) or ph <= HAZARD_PH_MIN or ph >= HAZARD_PH_MAX:
        return 0.0
    if 6.5 <= ph <= 8.5:
        if ph <= 7.0:
            return _clamp_0_100(80.0 + ((ph - 6.5) / 0.5) * 20.0)
        return _clamp_0_100(100.0 - ((ph - 7.0) / 1.5) * 20.0)
    if ph < 6.5:
        return _clamp_0_100(((ph - HAZARD_PH_MIN) / (6.5 - HAZARD_PH_MIN)) * 80.0)
    return _clamp_0_100(((HAZARD_PH_MAX - ph) / (HAZARD_PH_MAX - 8.5)) * 80.0)


def compute_subindex_tds(tds_ppm: float) -> float:
    """Normalizes TDS (ppm) onto [0, 100] using BIS IS 10500 (500 ppm) & hazard bound (700 ppm)."""
    if not math.isfinite(tds_ppm) or tds_ppm < 0.0 or tds_ppm >= HAZARD_TDS_MAX_PPM:
        return 0.0
    if tds_ppm <= 500.0:
        return _clamp_0_100(100.0 - (tds_ppm / 500.0) * 20.0)
    return _clamp_0_100(((HAZARD_TDS_MAX_PPM - tds_ppm) / (HAZARD_TDS_MAX_PPM - 500.0)) * 80.0)


def compute_subindex_turbidity(turb_ntu: float) -> float:
    """Normalizes Turbidity (NTU) onto [0, 100] using BIS (1 NTU), WHO (5 NTU) & hazard (150 NTU)."""
    if not math.isfinite(turb_ntu) or turb_ntu < 0.0 or turb_ntu >= HAZARD_TURB_MAX_NTU:
        return 0.0
    if turb_ntu <= 1.0:
        return _clamp_0_100(100.0 - turb_ntu * 20.0)
    if turb_ntu <= 5.0:
        return _clamp_0_100(80.0 - ((turb_ntu - 1.0) / 4.0) * 30.0)
    return _clamp_0_100(((HAZARD_TURB_MAX_NTU - turb_ntu) / (HAZARD_TURB_MAX_NTU - 5.0)) * 50.0)


@dataclass
class WqsResult:
    wqs: Optional[float] = None
    q_ph: Optional[float] = None
    q_tds: Optional[float] = None
    q_turb: Optional[float] = None
    water_status_code: int = -1
    water_status_label: str = "Fault"
    critical_hazard: bool = False
    hazard_reasons: List[str] = field(default_factory=list)


class WqsService:
    """Computes WQS and evaluates Critical Hazard Override rules."""

    @staticmethod
    def evaluate(
        ph_valid: bool,
        ph: Optional[float],
        turb_valid: bool,
        turbidity: Optional[float],
        tds_valid: bool,
        tds: Optional[float],
        turb_out_of_cal_range: bool = False,
        any_hardware_fault: bool = False,
    ) -> WqsResult:
        res = WqsResult()
        hazard_reasons: List[str] = []

        # 1. Critical Hazard Override (evaluated strictly on valid readings / healthy cal-range exceedance)
        if ph_valid and ph is not None and math.isfinite(ph):
            if ph < HAZARD_PH_MIN:
                hazard_reasons.append(f"CRITICAL HAZARD: pH ({ph:.2f}) below {HAZARD_PH_MIN:.1f}")
            elif ph > HAZARD_PH_MAX:
                hazard_reasons.append(f"CRITICAL HAZARD: pH ({ph:.2f}) above {HAZARD_PH_MAX:.1f}")

        if tds_valid and tds is not None and math.isfinite(tds) and tds > HAZARD_TDS_MAX_PPM:
            hazard_reasons.append(f"CRITICAL HAZARD: TDS ({tds:.0f} ppm) above {HAZARD_TDS_MAX_PPM:.0f} ppm")

        if turb_valid and turbidity is not None and math.isfinite(turbidity) and turbidity > HAZARD_TURB_MAX_NTU:
            hazard_reasons.append(f"CRITICAL HAZARD: Turbidity ({turbidity:.1f} NTU) above {HAZARD_TURB_MAX_NTU:.0f} NTU")

        if turb_out_of_cal_range:
            hazard_reasons.append("CRITICAL HAZARD: Turbidity outside valid calibration range")

        res.critical_hazard = len(hazard_reasons) > 0
        res.hazard_reasons = hazard_reasons

        # 2. Compute WQS ONLY when all 3 measurements are valid and finite
        if (
            ph_valid and ph is not None and math.isfinite(ph)
            and turb_valid and turbidity is not None and math.isfinite(turbidity)
            and tds_valid and tds is not None and math.isfinite(tds)
        ):
            q_ph = round(compute_subindex_ph(ph), 2)
            q_tds = round(compute_subindex_tds(tds), 2)
            q_turb = round(compute_subindex_turbidity(turbidity), 2)
            raw_wqs = (WQS_WEIGHT_TDS * q_tds) + (WQS_WEIGHT_PH * q_ph) + (WQS_WEIGHT_TURB * q_turb)
            res.q_ph = q_ph
            res.q_tds = q_tds
            res.q_turb = q_turb
            res.wqs = round(_clamp_0_100(raw_wqs), 2)

        # 3. Apply Critical Hazard Override immediately
        if res.critical_hazard:
            res.water_status_code = 0
            res.water_status_label = WATER_STATUS_LABELS[0]
            if res.wqs is not None and res.wqs > HAZARD_WQS_CAP:
                res.wqs = HAZARD_WQS_CAP
            return res

        # 4. Hardware fault or incomplete sensor triad -> Fault (-1), never Hazard
        if any_hardware_fault or res.wqs is None:
            res.water_status_code = -1
            res.water_status_label = WATER_STATUS_LABELS[-1]
            return res

        # 5. Map valid WQS to documented status codes
        if res.wqs >= 80.0:
            code = 4
        elif res.wqs >= 60.0:
            code = 3
        elif res.wqs >= 40.0:
            code = 2
        elif res.wqs > 20.0:
            code = 1
        else:
            code = 0

        res.water_status_code = code
        res.water_status_label = WATER_STATUS_LABELS[code]
        return res
