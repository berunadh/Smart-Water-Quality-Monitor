"""Feature engineering pipeline for water quality time-series."""

from typing import List, Dict, Any
import numpy as np
import pandas as pd


class WaterFeaturePipeline:
    """Transforms raw time-series sensor readings into feature vectors for ML models."""

    @staticmethod
    def readings_to_dataframe(readings: List[Dict[str, Any]]) -> pd.DataFrame:
        if not readings:
            return pd.DataFrame()

        df = pd.DataFrame(readings)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    @classmethod
    def extract_features(cls, df: pd.DataFrame, window_size: int = 5) -> pd.DataFrame:
        """
        Extracts rolling statistical features, differential rates of change,
        and optical-electrical stability metrics.
        """
        if df.empty or len(df) < window_size:
            return df

        features = df.copy()

        # Rolling statistics for pH
        if "ph" in features.columns:
            features["ph_rolling_mean"] = features["ph"].rolling(window=window_size, min_periods=1).mean()
            features["ph_rolling_std"] = features["ph"].rolling(window=window_size, min_periods=1).std().fillna(0.0)
            features["ph_diff_1"] = features["ph"].diff().fillna(0.0)

        # Rolling statistics for Turbidity
        if "turbidity" in features.columns:
            features["turb_rolling_mean"] = features["turbidity"].rolling(window=window_size, min_periods=1).mean()
            features["turb_rolling_std"] = features["turbidity"].rolling(window=window_size, min_periods=1).std().fillna(0.0)
            features["turb_diff_1"] = features["turbidity"].diff().fillna(0.0)

        # Rolling statistics for Calibrated TDS (preserves NaN where uncalibrated)
        if "tds" in features.columns and features["tds"].notna().any():
            features["tds_rolling_mean"] = features["tds"].rolling(window=window_size, min_periods=1).mean()
            features["tds_rolling_std"] = features["tds"].rolling(window=window_size, min_periods=1).std().fillna(0.0)
            features["tds_diff_1"] = features["tds"].diff().fillna(0.0)

        # Voltage stability (drift in hardware signal boards)
        if "ph_board_voltage" in features.columns:
            features["ph_v_drift"] = features["ph_board_voltage"].diff().abs().fillna(0.0)

        if "turbidity_board_voltage" in features.columns:
            features["turb_v_drift"] = features["turbidity_board_voltage"].diff().abs().fillna(0.0)

        if "tds_voltage" in features.columns and features["tds_voltage"].notna().any():
            features["tds_v_drift"] = features["tds_voltage"].diff().abs().fillna(0.0)

        return features
