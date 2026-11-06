"""Time-series trend analysis, drift detection, and diurnal statistics."""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from app.schemas.ml import TrendItem, TrendResponse


class TrendAnalyzer:
    """Analyzes continuous parameter degradation, baseline drift, and trends."""

    @staticmethod
    def calculate_linear_drift(timestamps: pd.Series, values: pd.Series, param_name: str) -> TrendItem:
        """Calculates linear slope (units per hour) and R-squared fit."""
        valid_mask = values.notna() & timestamps.notna()
        t = timestamps[valid_mask]
        v = values[valid_mask]

        if len(v) < 5:
            return TrendItem(
                parameter=param_name,
                slope_per_hour=0.0,
                intercept=None,
                r_squared=0.0,
                trend_direction="INSUFFICIENT_DATA",
                explanation=f"Insufficient calibrated data points ({len(v)} < 5) to compute {param_name} trend.",
            )

        # Convert timestamps to relative hours
        if not pd.api.types.is_datetime64_any_dtype(t):
            t = pd.to_datetime(t)

        t_seconds = (t - t.min()).dt.total_seconds().values
        t_hours = t_seconds / 3600.0

        if (t_hours.max() - t_hours.min()) < 1e-4:
            return TrendItem(
                parameter=param_name,
                slope_per_hour=0.0,
                intercept=float(v.mean()),
                r_squared=0.0,
                trend_direction="STABLE",
                explanation="Time span too short to compute rate of change.",
            )

        # Linear regression: v = m * t + c
        m, c = np.polyfit(t_hours, v.values, deg=1)
        corr_matrix = np.corrcoef(t_hours, v.values)
        r = corr_matrix[0, 1] if corr_matrix.shape == (2, 2) else 0.0
        r_squared = float(r ** 2) if not np.isnan(r) else 0.0

        # Significance thresholds
        # For pH: 0.05 units/hour is noticeable drift
        # For Turbidity: 0.2 NTU/hour is noticeable increase
        threshold_slope = 0.03 if param_name == "ph" else 0.15

        if abs(m) > threshold_slope and r_squared > 0.35:
            direction = "INCREASING" if m > 0 else "DECREASING"
            action = "rising" if m > 0 else "declining"
            explanation = (
                f"{param_name.upper()} is {action} at a rate of {abs(m):.3f} units/hour "
                f"(R² = {r_squared:.2f})."
            )
        else:
            direction = "STABLE"
            explanation = f"{param_name.upper()} baseline is stable (drift: {m:+.3f} units/hour, R² = {r_squared:.2f})."

        return TrendItem(
            parameter=param_name,
            slope_per_hour=round(float(m), 4),
            intercept=round(float(c), 3),
            r_squared=round(r_squared, 3),
            trend_direction=direction,
            explanation=explanation,
        )

    @classmethod
    def evaluate_water_trends(cls, df: pd.DataFrame, operating_mode: str = "real") -> TrendResponse:
        """Runs trend analysis across pH and Turbidity series."""
        if df.empty or "timestamp" not in df.columns:
            empty_item = TrendItem(
                parameter="none",
                slope_per_hour=0.0,
                r_squared=0.0,
                trend_direction="NO_DATA",
                explanation="No data available for trend evaluation.",
            )
            return TrendResponse(
                status="NO_DATA",
                operating_mode=operating_mode,
                ph_drift=empty_item,
                turbidity_drift=empty_item,
                total_samples=0,
            )

        ph_trend = cls.calculate_linear_drift(df["timestamp"], df.get("ph", pd.Series()), "ph")
        turb_trend = cls.calculate_linear_drift(df["timestamp"], df.get("turbidity", pd.Series()), "turbidity")

        return TrendResponse(
            status="SUCCESS",
            operating_mode=operating_mode,
            ph_drift=ph_trend,
            turbidity_drift=turb_trend,
            total_samples=len(df),
        )
