"""Persistent Water Quality Mode management and threshold evaluation engine."""

from typing import Optional, Dict, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.water_quality_config import WaterQualityConfigModel
from app.models.water_reading import WaterReadingModel
from app.schemas.mode import (
    WaterQualityModeLiteral,
    ModeThresholdProfile,
    ThresholdUpdateRequest,
    ParameterEvaluation,
    WaterQualityEvaluation,
    WaterQualitySettingsResponse,
)


DRINKING_DISCLAIMER = (
    "Preliminary physicochemical monitoring against BIS IS 10500:2012 acceptable limits "
    "(pH 6.5–8.5, Turbidity ≤ 1 NTU, TDS ≤ 500 mg/L). Physical sensors do NOT detect "
    "microbiological pathogens, heavy metals, or chemical toxins and do not certify potability."
)

REGULAR_USAGE_DISCLAIMER = (
    "Evaluated against user-configurable operational thresholds for general non-drinking usage. "
    "No universal regulatory standard applies to every non-drinking application; adjust limits for your intended use."
)


class ModeService:
    """Manages Drinking Mode vs Regular Usage Mode profiles and evaluations."""

    @staticmethod
    def get_or_create_config(db: Session) -> WaterQualityConfigModel:
        config = db.query(WaterQualityConfigModel).filter(WaterQualityConfigModel.id == 1).first()
        if not config:
            config = WaterQualityConfigModel(
                id=1,
                active_mode="drinking",
                drinking_ph_min=6.5,
                drinking_ph_max=8.5,
                drinking_turbidity_max=1.0,
                drinking_tds_max=500.0,
                regular_ph_min=6.0,
                regular_ph_max=9.0,
                regular_turbidity_max=10.0,
                regular_tds_max=1000.0,
            )
            db.add(config)
            db.commit()
            db.refresh(config)
        return config

    @staticmethod
    def build_profile(config: WaterQualityConfigModel, mode: WaterQualityModeLiteral) -> ModeThresholdProfile:
        if mode == "drinking":
            return ModeThresholdProfile(
                ph_min=config.drinking_ph_min,
                ph_max=config.drinking_ph_max,
                turbidity_max=config.drinking_turbidity_max,
                tds_max=config.drinking_tds_max,
                label="Drinking Mode",
                reference_note="BIS IS 10500:2012 Acceptable Limits (Preliminary Monitoring Only)",
                is_regulatory_reference=True,
            )
        return ModeThresholdProfile(
            ph_min=config.regular_ph_min,
            ph_max=config.regular_ph_max,
            turbidity_max=config.regular_turbidity_max,
            tds_max=config.regular_tds_max,
            label="Regular Usage Mode",
            reference_note="User-Configurable Non-Drinking Operational Settings (Provisional Defaults)",
            is_regulatory_reference=False,
        )

    @classmethod
    def get_active_profile(cls, db: Session) -> ModeThresholdProfile:
        config = cls.get_or_create_config(db)
        mode: WaterQualityModeLiteral = "drinking" if config.active_mode == "drinking" else "regular_usage"
        return cls.build_profile(config, mode)

    @classmethod
    def evaluate_reading(
        cls,
        reading: Optional[WaterReadingModel],
        config: WaterQualityConfigModel,
    ) -> WaterQualityEvaluation:
        mode: WaterQualityModeLiteral = "drinking" if config.active_mode == "drinking" else "regular_usage"
        profile = cls.build_profile(config, mode)
        disclaimer = DRINKING_DISCLAIMER if mode == "drinking" else REGULAR_USAGE_DISCLAIMER

        if reading is None:
            empty_eval = {
                "ph": ParameterEvaluation(
                    parameter="pH",
                    status="unavailable",
                    value=None,
                    unit="pH",
                    limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                    message="No telemetry received.",
                ),
                "turbidity": ParameterEvaluation(
                    parameter="Turbidity",
                    status="unavailable",
                    value=None,
                    unit="NTU",
                    limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                    message="No telemetry received.",
                ),
                "tds": ParameterEvaluation(
                    parameter="TDS",
                    status="unavailable",
                    value=None,
                    unit="mg/L",
                    limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                    message="No telemetry received.",
                ),
            }
            return WaterQualityEvaluation(
                active_mode=mode,
                mode_label=profile.label,
                overall_status="NO_DATA",
                alert_severity=0,
                violated_parameters=[],
                parameter_evaluations=empty_eval,
                preliminary_disclaimer=disclaimer,
            )

        violated: List[str] = []
        param_evals: Dict[str, ParameterEvaluation] = {}
        max_severity = 0
        any_uncalibrated = False
        has_fault = (not reading.is_valid) or bool(reading.health_code & (1 << 4))

        # 1. pH evaluation
        ph_fault = bool(reading.health_code & (1 << 2)) or (
            not reading.is_valid and (reading.ph is None or (reading.ph_voltage * 0.40 >= 3.05))
        )
        if ph_fault:
            param_evals["ph"] = ParameterEvaluation(
                parameter="pH",
                status="fault",
                value=None,
                unit="pH",
                limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                message="pH sensor fault or electrical out-of-range.",
            )
            has_fault = True
        elif not reading.ph_calibrated or reading.ph is None:
            any_uncalibrated = True
            param_evals["ph"] = ParameterEvaluation(
                parameter="pH",
                status="uncalibrated",
                value=None,
                unit="pH",
                limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                message="pH calibration pending (buffer calibration required).",
            )
        else:
            v = reading.ph
            margin = min(0.2, (profile.ph_max - profile.ph_min) * 0.1)
            if v < profile.ph_min or v > profile.ph_max:
                violated.append(f"pH ({v:.2f}) exceeded the allowed range ({profile.ph_min:.1f}–{profile.ph_max:.1f})")
                sev = 2 if (v < profile.ph_min - 1.0 or v > profile.ph_max + 1.0) else 1
                max_severity = max(max_severity, sev)
                param_evals["ph"] = ParameterEvaluation(
                    parameter="pH",
                    status="exceeded",
                    value=v,
                    unit="pH",
                    limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                    message=f"pH ({v:.2f}) exceeded allowed range.",
                )
            elif v < profile.ph_min + margin or v > profile.ph_max - margin:
                param_evals["ph"] = ParameterEvaluation(
                    parameter="pH",
                    status="warning",
                    value=v,
                    unit="pH",
                    limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                    message=f"pH ({v:.2f}) approaching mode limit.",
                )
            else:
                param_evals["ph"] = ParameterEvaluation(
                    parameter="pH",
                    status="acceptable",
                    value=v,
                    unit="pH",
                    limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                    message=f"pH ({v:.2f}) within limits.",
                )

        # 2. Turbidity evaluation
        turb_fault = bool(reading.health_code & (1 << 3)) or (
            not reading.is_valid and (reading.turbidity is None or (reading.turbidity_voltage * 0.40 >= 3.05))
        )
        if turb_fault:
            param_evals["turbidity"] = ParameterEvaluation(
                parameter="Turbidity",
                status="fault",
                value=None,
                unit="NTU",
                limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                message="Turbidity sensor fault or disconnected.",
            )
            has_fault = True
        elif not reading.turbidity_calibrated or reading.turbidity is None:
            any_uncalibrated = True
            param_evals["turbidity"] = ParameterEvaluation(
                parameter="Turbidity",
                status="uncalibrated",
                value=None,
                unit="NTU",
                limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                message="Turbidity calibration pending.",
            )
        else:
            v = reading.turbidity
            warn_floor = profile.turbidity_max * 0.85
            if v > profile.turbidity_max:
                violated.append(
                    f"Turbidity ({v:.2f} NTU) exceeded the selected threshold (≤ {profile.turbidity_max:.1f} NTU)"
                )
                sev = 2 if v >= max(5.0, profile.turbidity_max * 2.5) else 1
                max_severity = max(max_severity, sev)
                param_evals["turbidity"] = ParameterEvaluation(
                    parameter="Turbidity",
                    status="exceeded",
                    value=v,
                    unit="NTU",
                    limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                    message=f"Turbidity ({v:.2f} NTU) exceeded threshold.",
                )
            elif v > warn_floor:
                param_evals["turbidity"] = ParameterEvaluation(
                    parameter="Turbidity",
                    status="warning",
                    value=v,
                    unit="NTU",
                    limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                    message=f"Turbidity ({v:.2f} NTU) approaching limit.",
                )
            else:
                param_evals["turbidity"] = ParameterEvaluation(
                    parameter="Turbidity",
                    status="acceptable",
                    value=v,
                    unit="NTU",
                    limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                    message=f"Turbidity ({v:.2f} NTU) within limit.",
                )

        # 3. TDS evaluation
        tds_unavailable = bool(reading.health_code & (1 << 5)) and reading.tds is None and not reading.tds_calibrated
        tds_fault = bool(reading.health_code & (1 << 8)) or (
            reading.tds_voltage is not None and reading.tds_voltage >= 3.05
        )
        if tds_fault:
            param_evals["tds"] = ParameterEvaluation(
                parameter="TDS",
                status="fault",
                value=None,
                unit="mg/L",
                limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                message="TDS probe disconnected or out-of-range.",
            )
            has_fault = True
        elif tds_unavailable and reading.tds_voltage is None:
            any_uncalibrated = True
            param_evals["tds"] = ParameterEvaluation(
                parameter="TDS",
                status="unavailable",
                value=None,
                unit="mg/L",
                limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                message="TDS unavailable or uncalibrated (GPIO35).",
            )
        elif not reading.tds_calibrated or reading.tds is None:
            any_uncalibrated = True
            param_evals["tds"] = ParameterEvaluation(
                parameter="TDS",
                status="uncalibrated",
                value=None,
                unit="mg/L",
                limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                message="TDS calibration pending (null until calibrated).",
            )
        else:
            v = reading.tds
            warn_floor = profile.tds_max * 0.90
            if v > profile.tds_max:
                violated.append(f"TDS ({v:.0f} mg/L) exceeded the selected threshold (≤ {profile.tds_max:.0f} mg/L)")
                sev = 2 if v >= profile.tds_max * 1.5 else 1
                max_severity = max(max_severity, sev)
                param_evals["tds"] = ParameterEvaluation(
                    parameter="TDS",
                    status="exceeded",
                    value=v,
                    unit="mg/L",
                    limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                    message=f"TDS ({v:.0f} mg/L) exceeded threshold.",
                )
            elif v > warn_floor:
                param_evals["tds"] = ParameterEvaluation(
                    parameter="TDS",
                    status="warning",
                    value=v,
                    unit="mg/L",
                    limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                    message=f"TDS ({v:.0f} mg/L) approaching limit.",
                )
            else:
                param_evals["tds"] = ParameterEvaluation(
                    parameter="TDS",
                    status="acceptable",
                    value=v,
                    unit="mg/L",
                    limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                    message=f"TDS ({v:.0f} mg/L) within limit.",
                )

        # Determine overall status
        has_warning_param = any(e.status == "warning" for e in param_evals.values())
        if max_severity >= 2:
            overall_status = "CRITICAL"
        elif max_severity == 1:
            overall_status = "EXCEEDED"
        elif has_fault:
            overall_status = "SENSOR_FAULT"
            max_severity = 3
        elif any_uncalibrated:
            overall_status = "CALIBRATION_PENDING"
        elif has_warning_param:
            overall_status = "WARNING"
        else:
            overall_status = "NORMAL"

        return WaterQualityEvaluation(
            active_mode=mode,
            mode_label=profile.label,
            overall_status=overall_status,
            alert_severity=max_severity,
            violated_parameters=violated,
            parameter_evaluations=param_evals,
            preliminary_disclaimer=disclaimer,
        )

    @classmethod
    def get_settings_response(cls, db: Session) -> WaterQualitySettingsResponse:
        config = cls.get_or_create_config(db)
        mode: WaterQualityModeLiteral = "drinking" if config.active_mode == "drinking" else "regular_usage"
        latest = db.query(WaterReadingModel).order_by(WaterReadingModel.timestamp.desc()).first()
        evaluation = cls.evaluate_reading(latest, config)
        return WaterQualitySettingsResponse(
            active_mode=mode,
            active_profile=cls.build_profile(config, mode),
            drinking_profile=cls.build_profile(config, "drinking"),
            regular_usage_profile=cls.build_profile(config, "regular_usage"),
            preliminary_disclaimer=DRINKING_DISCLAIMER if mode == "drinking" else REGULAR_USAGE_DISCLAIMER,
            updated_at=config.updated_at or datetime.utcnow(),
            latest_evaluation=evaluation,
        )

    @classmethod
    def switch_mode(cls, db: Session, new_mode: WaterQualityModeLiteral) -> WaterQualitySettingsResponse:
        config = cls.get_or_create_config(db)
        config.active_mode = new_mode
        config.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(config)
        return cls.get_settings_response(db)

    @classmethod
    def update_thresholds(cls, db: Session, req: ThresholdUpdateRequest) -> WaterQualitySettingsResponse:
        config = cls.get_or_create_config(db)
        if req.mode == "drinking":
            config.drinking_ph_min = req.ph_min
            config.drinking_ph_max = req.ph_max
            config.drinking_turbidity_max = req.turbidity_max
            config.drinking_tds_max = req.tds_max
        else:
            config.regular_ph_min = req.ph_min
            config.regular_ph_max = req.ph_max
            config.regular_turbidity_max = req.turbidity_max
            config.regular_tds_max = req.tds_max
        config.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(config)
        return cls.get_settings_response(db)

    @classmethod
    def reset_mode_defaults(cls, db: Session, mode: WaterQualityModeLiteral) -> WaterQualitySettingsResponse:
        config = cls.get_or_create_config(db)
        if mode == "drinking":
            config.drinking_ph_min = 6.5
            config.drinking_ph_max = 8.5
            config.drinking_turbidity_max = 1.0
            config.drinking_tds_max = 500.0
        else:
            config.regular_ph_min = 6.0
            config.regular_ph_max = 9.0
            config.regular_turbidity_max = 10.0
            config.regular_tds_max = 1000.0
        config.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(config)
        return cls.get_settings_response(db)
