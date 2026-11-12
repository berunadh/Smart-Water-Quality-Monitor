"""Persistent Water Quality Mode management and threshold evaluation engine."""

from typing import Optional, Dict, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.water_quality_config import WaterQualityConfigModel
from app.models.water_reading import WaterReadingModel
from app.services.wqs_service import WqsService
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

        # 1. pH evaluation (distinguishes disconnected vs fault vs provisional vs calibration pending)
        ph_disconnected = bool(reading.health_code & (1 << 2)) and ((reading.ph_voltage * 0.40) < 0.08)
        ph_fault = bool(reading.health_code & (1 << 2)) or (
            not reading.is_valid and (reading.ph is None or (reading.ph_voltage * 0.40 >= 3.05))
        )
        ph_prov_flag = bool(reading.health_code & (1 << 12))
        ph_provisional = (ph_prov_flag or (not reading.ph_calibrated)) and reading.ph is not None
        if ph_prov_flag or (not reading.ph_calibrated):
            any_uncalibrated = True

        if ph_disconnected:
            param_evals["ph"] = ParameterEvaluation(
                parameter="pH",
                status="disconnected",
                value=None,
                unit="pH",
                limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                message="pH probe disconnected or reading ~0V.",
            )
            has_fault = True
        elif ph_fault:
            param_evals["ph"] = ParameterEvaluation(
                parameter="pH",
                status="fault",
                value=None,
                unit="pH",
                limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                message="pH sensor fault or electrical out-of-range.",
            )
            has_fault = True
        elif reading.ph is None or (not reading.ph_calibrated and not ph_provisional):
            any_uncalibrated = True
            ph_msg = (
                "pH is a model-based provisional estimate; buffer calibration is still required."
                if ph_prov_flag
                else "pH calibration pending (E201-C buffers and measured board voltages required)."
            )
            param_evals["ph"] = ParameterEvaluation(
                parameter="pH",
                status="uncalibrated",
                value=None,
                unit="pH",
                limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                message=ph_msg,
            )
        elif ph_provisional:
            param_evals["ph"] = ParameterEvaluation(
                parameter="pH",
                status="provisional",
                value=reading.ph,
                unit="pH",
                limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                message="Model-based pH estimate; not used for threshold alerts until buffer-verified.",
            )
        else:
            v = reading.ph
            prov_note = " (provisional estimate)" if ph_provisional else ""
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
                    message=f"pH ({v:.2f}) exceeded allowed range{prov_note}.",
                )
            elif v < profile.ph_min + margin or v > profile.ph_max - margin:
                param_evals["ph"] = ParameterEvaluation(
                    parameter="pH",
                    status="warning",
                    value=v,
                    unit="pH",
                    limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                    message=f"pH ({v:.2f}) approaching mode limit{prov_note}.",
                )
            else:
                param_evals["ph"] = ParameterEvaluation(
                    parameter="pH",
                    status="acceptable",
                    value=v,
                    unit="pH",
                    limit_text=f"{profile.ph_min:.1f}–{profile.ph_max:.1f}",
                    message=f"pH ({v:.2f}) within limits{prov_note}.",
                )

        # 2. Turbidity evaluation (distinguishes disconnected vs fault vs provisional vs calibration pending)
        turb_disconnected = bool(reading.health_code & (1 << 3)) and ((reading.turbidity_voltage * 0.40) < 0.08)
        turb_fault = bool(reading.health_code & (1 << 3)) or (
            not reading.is_valid and (reading.turbidity is None or (reading.turbidity_voltage * 0.40 >= 3.05))
        )
        turb_prov_flag = bool(reading.health_code & (1 << 13))
        turb_provisional = (turb_prov_flag or (not reading.turbidity_calibrated)) and reading.turbidity is not None
        if turb_prov_flag or (not reading.turbidity_calibrated):
            any_uncalibrated = True

        if turb_disconnected:
            param_evals["turbidity"] = ParameterEvaluation(
                parameter="Turbidity",
                status="disconnected",
                value=None,
                unit="NTU",
                limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                message="Turbidity probe disconnected (~0V; not clear water).",
            )
            has_fault = True
        elif turb_fault:
            param_evals["turbidity"] = ParameterEvaluation(
                parameter="Turbidity",
                status="fault",
                value=None,
                unit="NTU",
                limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                message="Turbidity sensor fault or out-of-range.",
            )
            has_fault = True
        elif reading.turbidity is None or (not reading.turbidity_calibrated and not turb_provisional):
            any_uncalibrated = True
            turb_msg = (
                "Turbidity is a model-based provisional estimate; certified standards are still required."
                if turb_prov_flag
                else "Turbidity calibration pending (actual optical-module standards required)."
            )
            param_evals["turbidity"] = ParameterEvaluation(
                parameter="Turbidity",
                status="uncalibrated",
                value=None,
                unit="NTU",
                limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                message=turb_msg,
            )
        elif turb_provisional:
            param_evals["turbidity"] = ParameterEvaluation(
                parameter="Turbidity",
                status="provisional",
                value=reading.turbidity,
                unit="NTU",
                limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                message="Provisional reference-anchor NTU estimate; certified standards still required.",
            )
        else:
            v = reading.turbidity
            prov_note = " (provisional estimate)" if turb_provisional else ""
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
                    message=f"Turbidity ({v:.2f} NTU) exceeded threshold{prov_note}.",
                )
            elif v > warn_floor:
                param_evals["turbidity"] = ParameterEvaluation(
                    parameter="Turbidity",
                    status="warning",
                    value=v,
                    unit="NTU",
                    limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                    message=f"Turbidity ({v:.2f} NTU) approaching limit{prov_note}.",
                )
            else:
                param_evals["turbidity"] = ParameterEvaluation(
                    parameter="Turbidity",
                    status="acceptable",
                    value=v,
                    unit="NTU",
                    limit_text=f"≤ {profile.turbidity_max:.1f} NTU",
                    message=f"Turbidity ({v:.2f} NTU) within limit{prov_note}.",
                )

        # 3. TDS evaluation (distinguishes valid, provisional, dry, disconnected, fault, unavailable, pending)
        tds_unavailable = bool(reading.health_code & (1 << 5)) and reading.tds is None and not reading.tds_calibrated
        tds_dry = bool(reading.health_code & (1 << 10)) and reading.tds is None
        tds_provisional = bool(reading.health_code & (1 << 11)) and reading.tds is not None
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
        elif tds_dry:
            param_evals["tds"] = ParameterEvaluation(
                parameter="TDS",
                status="dry",
                value=None,
                unit="mg/L",
                limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                message="TDS probe dry / not immersed (never 0 ppm).",
            )
        elif tds_unavailable and reading.tds_voltage is None:
            any_uncalibrated = True
            param_evals["tds"] = ParameterEvaluation(
                parameter="TDS",
                status="unavailable",
                value=None,
                unit="mg/L",
                limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                message="TDS unavailable or disabled (GPIO35).",
            )
        elif (not reading.tds_calibrated and not tds_provisional) or reading.tds is None:
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
            prov_note = " (provisional 25°C polynomial)" if tds_provisional else ""
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
                    message=f"TDS ({v:.0f} mg/L) exceeded threshold{prov_note}.",
                )
            elif v > warn_floor:
                param_evals["tds"] = ParameterEvaluation(
                    parameter="TDS",
                    status="warning",
                    value=v,
                    unit="mg/L",
                    limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                    message=f"TDS ({v:.0f} mg/L) approaching limit{prov_note}.",
                )
            else:
                param_evals["tds"] = ParameterEvaluation(
                    parameter="TDS",
                    status="acceptable",
                    value=v,
                    unit="mg/L",
                    limit_text=f"≤ {profile.tds_max:.0f} mg/L",
                    message=f"TDS ({v:.0f} mg/L) within limit{prov_note}.",
                )

        # Evaluate WQS & Critical Hazard Override (Sections 7 & 8)
        ph_valid_meas = (not ph_fault) and reading.ph_calibrated and (reading.ph is not None)
        turb_valid_meas = (not turb_fault) and reading.turbidity_calibrated and (reading.turbidity is not None)
        tds_valid_meas = (not tds_fault) and (not tds_dry) and (not tds_unavailable) and (reading.tds_calibrated or tds_provisional) and (reading.tds is not None)
        alert_txt = ((reading.alert_messages or "") + " " + (reading.validation_notes or "")).upper()
        turb_out_of_cal_range = (
            ("OUT OF CAL RANGE" in alert_txt or "TURB-RNG" in alert_txt)
            and (not turb_fault)
            and (not turb_prov_flag)
        )

        # Only missing readings or hardware faults/dry probe invalidate WQS;
        # provisional estimates with all 3 valid numeric values can compute provisional WQS
        # while HEALTH_CALIBRATION_PENDING keeps experimental status pending.
        missing_numeric = (reading.ph is None) or (reading.turbidity is None) or (reading.tds is None)
        wqs_res = WqsService.evaluate(
            ph_valid=ph_valid_meas,
            ph=reading.ph,
            turb_valid=turb_valid_meas,
            turbidity=reading.turbidity,
            tds_valid=tds_valid_meas,
            tds=reading.tds,
            turb_out_of_cal_range=turb_out_of_cal_range,
            any_hardware_fault=has_fault or missing_numeric or tds_dry,
        )

        if wqs_res.critical_hazard:
            max_severity = 2
            for reason in wqs_res.hazard_reasons:
                if reason not in violated:
                    violated.append(reason)

        # Determine overall status
        has_warning_param = any(e.status == "warning" for e in param_evals.values())
        if max_severity >= 2 or wqs_res.critical_hazard:
            overall_status = "CRITICAL"
            max_severity = 2
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
            wqs=wqs_res.wqs,
            q_ph=wqs_res.q_ph,
            q_turb=wqs_res.q_turb,
            q_tds=wqs_res.q_tds,
            water_status_code=wqs_res.water_status_code,
            water_status_label=wqs_res.water_status_label,
            critical_hazard=wqs_res.critical_hazard,
            hazard_reasons=wqs_res.hazard_reasons,
        )

    @staticmethod
    def get_latest_preferred_reading(db: Session) -> Optional[WaterReadingModel]:
        """Returns latest real reading when DATA_MODE=='real' and real data exists; avoids stale demo shadowing."""
        from app.core.config import settings
        if settings.DATA_MODE == "real":
            real_latest = (
                db.query(WaterReadingModel)
                .filter(WaterReadingModel.operating_mode == "real")
                .order_by(WaterReadingModel.timestamp.desc())
                .first()
            )
            if real_latest is not None:
                return real_latest
        return db.query(WaterReadingModel).order_by(WaterReadingModel.timestamp.desc()).first()

    @classmethod
    def get_settings_response(cls, db: Session) -> WaterQualitySettingsResponse:
        config = cls.get_or_create_config(db)
        mode: WaterQualityModeLiteral = "drinking" if config.active_mode == "drinking" else "regular_usage"
        latest = cls.get_latest_preferred_reading(db)
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
