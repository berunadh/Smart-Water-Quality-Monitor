"""One profile contract for presentation telemetry; never fabricates physical pH."""
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.sample_profile import SampleProfileStateModel
from app.models.water_reading import WaterReadingModel


PROFILES = {
    "kent_ro": {"label": "Kent RO Water", "ph_adc": 1.908, "ph_board": 4.770,
                 "turb_board": 0.939, "tds_adc": 0.307, "demo_ph": 7.00},
    "household_tap": {"label": "Household Tap Water", "ph_adc": 1.908, "ph_board": 4.770,
                      "turb_board": 1.484, "tds_adc": 2.155, "demo_ph": 7.20},
}


def _tds(v: float) -> float:
    return 0.5 * (133.42 * v ** 3 - 255.86 * v ** 2 + 857.39 * v)


def _turb(v: float) -> float:
    """Provisional reference-anchor NTU model (RO 0.939V -> 0.50 NTU, Tap 1.484V -> 3.20 NTU)."""
    ro_v, ro_ntu = 0.939, 0.50
    tap_v, tap_ntu = 1.484, 3.20
    min_v, floor_ntu = 0.20, 0.15
    if v < min_v:
        return floor_ntu
    if v < ro_v:
        return floor_ntu + ((v - min_v) / (ro_v - min_v)) * (ro_ntu - floor_ntu)
    slope = (tap_ntu - ro_ntu) / (tap_v - ro_v)
    return max(0.0, min(100.0, ro_ntu + slope * (v - ro_v)))


class SampleProfileService:
    @staticmethod
    def get_or_create(db: Session) -> SampleProfileStateModel:
        state = db.query(SampleProfileStateModel).filter_by(id=1).first()
        if state is None:
            state = SampleProfileStateModel(id=1)
            db.add(state); db.commit(); db.refresh(state)
        return state

    @classmethod
    def describe(cls, state: SampleProfileStateModel) -> dict:
        return {"selected_profile": state.selected_profile, "contaminated_demo_ph": state.contaminated_demo_ph,
                "updated_at": state.updated_at,
                "control_note": "Presentation state is explicit DEMO_ESTIMATE data. It does not recalibrate or overwrite the ESP32 sensor."}

    @classmethod
    def make_reading(cls, state: SampleProfileStateModel, timestamp: Optional[datetime] = None) -> WaterReadingModel:
        profile = state.selected_profile
        base = PROFILES.get(profile, PROFILES["kent_ro"])
        # The board is saturated/unchanged for both measured references: no defensible physical pH estimate.
        ph_demo = state.contaminated_demo_ph if profile == "contaminated_demo" else base["demo_ph"]
        if profile == "contaminated_demo":
            # Actual salt/dirt hardware measurements must replace these reference voltages in live mode.
            turb_v, tds_v = 0.939, 0.307
            notes = "DEMO_ESTIMATE: adjust pH explicitly; salt/dirt require actual TDS/turbidity hardware response."
        else:
            turb_v, tds_v = base["turb_board"], base["tds_adc"]
            notes = "REFERENCE PROFILE: measured voltages; pH interface response unchanged/suspect, so pH is DEMO_ESTIMATE."
        return WaterReadingModel(
            timestamp=timestamp or datetime.utcnow(), ph=round(ph_demo, 2), ph_sensor_estimate=None,
            ph_demo_estimate=round(ph_demo, 2), ph_display_source="DEMO_ESTIMATE", turbidity=round(_turb(turb_v), 2),
            tds=round(_tds(tds_v), 1), ph_voltage=base.get("ph_board", 4.770), turbidity_voltage=turb_v,
            tds_voltage=tds_v, ph_calibrated=False, turbidity_calibrated=False, tds_calibrated=False,
            # all estimates remain provisional; presentation profile alone cannot produce a safety declaration.
            alert_severity=0, health_code=(1 << 7) | (1 << 11) | (1 << 12) | (1 << 13),
            sensor_health_summary="DEMO_ESTIMATE / PH_RESPONSE_SUSPECT", alert_messages="REFERENCE / DEMO PROFILE",
            data_source="simulated", operating_mode="demo", water_quality_mode="drinking", sample_profile=profile,
            is_valid=True, is_stale=False, validation_notes=notes,
        )
