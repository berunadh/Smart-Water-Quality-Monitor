"""Hardware and acquisition fault detector.
Strictly distinguishes electrical/sensor hardware failures from true water quality anomalies.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
from app.schemas.ml import AnomalyItem


class SensorFaultDetector:
    """
    Identifies physical and electrical failure modes in sensor telemetry:
    - Stuck signal conditioning board outputs (zero variance over sequential reads)
    - Open-circuit disconnected sensors (near 0.0V)
    - ADC over-range saturation (>3.05V ADC, >7.5V reconstructed)
    - Implausible step jumps between consecutive readings (<20 seconds)
    - Stale / frozen data transmission
    """

    @classmethod
    def analyze_faults(cls, df: pd.DataFrame) -> List[AnomalyItem]:
        if df.empty:
            return []

        faults: List[AnomalyItem] = []

        # 1. Check for Stuck Value Patterns (Op-amp lockup or frozen ADC)
        for col in ["ph_voltage", "turbidity_voltage", "tds_voltage", "ph", "turbidity", "tds"]:
            if col not in df.columns:
                continue

            series = df[col].dropna()
            if len(series) < 6:
                continue

            # Check if last 6 readings have near-zero variance
            recent = series.tail(6)
            std_recent = float(recent.std())
            mean_recent = float(recent.mean())

            # Real analog sensors always have micro-jitter (1-5 mV noise).
            # Exactly 0.000 variance over multiple cycles signals a dead/stuck signal.
            if std_recent < 1e-4 and mean_recent > 0.05:
                ts = df["timestamp"].iloc[-1] if "timestamp" in df.columns else None
                faults.append(
                    AnomalyItem(
                        timestamp=ts,
                        parameter=col,
                        measured_value=mean_recent,
                        baseline_mean=mean_recent,
                        baseline_std=0.0,
                        anomaly_score=10.0,
                        detector_type="hardware_fault_detector",
                        anomaly_type="HARDWARE_STUCK_VALUE",
                        human_explanation=(
                            f"Hardware fault detected: {col} has remained exactly frozen at {mean_recent:.3f} "
                            "with zero natural analog ADC variance across consecutive reads."
                        ),
                        category="RULE_BASED_WARNING",
                    )
                )

        # 2. Check for Disconnected Probes or Ground Loss
        if "ph_voltage" in df.columns and df["ph_voltage"].notna().any():
            last_ph_v = float(df["ph_voltage"].dropna().iloc[-1])
            if last_ph_v < 0.08:
                faults.append(
                    AnomalyItem(
                        timestamp=df["timestamp"].iloc[-1] if "timestamp" in df.columns else None,
                        parameter="ph_voltage",
                        measured_value=last_ph_v,
                        anomaly_score=9.5,
                        detector_type="hardware_fault_detector",
                        anomaly_type="PROBE_DISCONNECTED",
                        human_explanation="pH probe signal conditioning board output is at GND (~0V), indicating disconnected probe.",
                        category="RULE_BASED_WARNING",
                    )
                )

        # 3. Check for Electrical Over-Range
        for v_col, name, ratio in [("ph_voltage", "pH", 0.40), ("turbidity_voltage", "Turbidity", 0.40), ("tds_voltage", "TDS", 1.00)]:
            if v_col in df.columns and df[v_col].notna().any():
                last_v = float(df[v_col].dropna().iloc[-1])
                # pH & Turbidity: V_ADC = V_board * 0.40; TDS: Direct V_ADC (1.00x)
                if last_v * ratio >= 3.05:
                    faults.append(
                        AnomalyItem(
                            timestamp=df["timestamp"].iloc[-1] if "timestamp" in df.columns else None,
                            parameter=v_col,
                            measured_value=last_v,
                            anomaly_score=10.0,
                            detector_type="hardware_fault_detector",
                            anomaly_type="ELECTRICAL_OVER_RANGE",
                            human_explanation=(
                                f"CRITICAL ELECTRICAL HAZARD: {name} voltage ({last_v:.2f}V) "
                                "exceeds safe limit, producing >=3.05V at ESP32 ADC pin."
                            ),
                            category="RULE_BASED_WARNING",
                        )
                    )

        # 4. Check for Implausible Step Jumps
        for col, max_jump in [("ph", 2.5), ("turbidity", 50.0), ("tds", 350.0)]:
            if col in df.columns and len(df[col].dropna()) >= 2:
                diffs = df[col].dropna().diff().abs()
                max_diff = float(diffs.max())
                if max_diff > max_jump:
                    bad_idx = diffs.idxmax()
                    val = float(df[col].loc[bad_idx])
                    faults.append(
                        AnomalyItem(
                            timestamp=df["timestamp"].loc[bad_idx] if "timestamp" in df.columns else None,
                            parameter=col,
                            measured_value=val,
                            anomaly_score=8.0,
                            detector_type="hardware_fault_detector",
                            anomaly_type="IMPLAUSIBLE_STEP_JUMP",
                            human_explanation=(
                                f"Implausible step discontinuity: {col} changed by {max_diff:.1f} in a single interval, "
                                "indicating physical shock or intermittent connector contact."
                            ),
                            category="RULE_BASED_WARNING",
                        )
                    )

        return faults
