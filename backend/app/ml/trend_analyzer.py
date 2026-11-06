"""Time-series trend analysis, drift detection, and diurnal statistics."""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd


class TrendAnalyzer:
    """Analyzes continuous degradation, sensor drift, and seasonal trends."""

    @staticmethod
    def calculate_linear_drift(timestamps: pd.Series, values: pd.Series) -> Dict[str, Any]:
        """Calculates linear slope (units per hour) and R-squared fit."""
        valid_mask = values.notna() & timestamps.notna()
        t = timestamps[valid_mask]
        v = values[valid_mask]

        if len(v) < 5:
            return {"slope_per_hour": 0.0, "r_squared": 0.0, "trend": "INSUFFICIENT_DATA"}

        # Convert timestamps to relative hours
        t_seconds = (t - t.min()).dt.total_seconds().values
        t_hours = t_seconds / 3600.0

        # Linear regression fit: v = m * t + c
        m, c = np.polyfit(t_hours, v.values, deg=1)
        correlation_matrix = np.corrcoef(t_hours, v.values)
        r = correlation_matrix[0, 1] if correlation_matrix.shape == (2, 2) else 0.0
        r_squared = float(r ** 2) if not np.isnan(r) else 0.0

        trend_direction = "STABLE"
        if abs(m) > 0.02 and r_squared > 0.4:
            trend_direction = "INCREASING" if m > 0 else "DECREASING"

        return {
            "slope_per_hour": float(m),
            "intercept": float(c),
            "r_squared": r_squared,
            "trend": trend_direction,
        }

    @classmethod
    def evaluate_water_trends(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Runs trend analysis across pH and Turbidity series."""
        if df.empty or "timestamp" not in df.columns:
            return {"status": "NO_DATA"}

        ph_trend = {}
        turb_trend = {}

        if "ph" in df.columns:
            ph_trend = cls.calculate_linear_drift(df["timestamp"], df["ph"])

        if "turbidity" in df.columns:
            turb_trend = cls.calculate_linear_drift(df["timestamp"], df["turbidity"])

        return {
            "ph_drift": ph_trend,
            "turbidity_drift": turb_trend,
            "total_samples": len(df),
        }
