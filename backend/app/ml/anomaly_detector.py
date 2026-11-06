"""Machine learning and statistical anomaly detection architectures."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd


class BaseAnomalyDetector(ABC):
    @abstractmethod
    def fit(self, data: pd.DataFrame) -> None:
        """Fits the detector to baseline normal water sensor data."""
        pass

    @abstractmethod
    def predict(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Identifies anomalies in new water telemetry batches."""
        pass


class ZScoreAnomalyDetector(BaseAnomalyDetector):
    """
    Statistical Moving Z-Score Anomaly Detector.
    Requires no pre-trained weights; computes dynamic statistical thresholds
    over a rolling window to identify abrupt spikes or baseline contamination.
    """

    def __init__(self, threshold: float = 3.0, min_history: int = 10):
        self.threshold = threshold
        self.min_history = min_history
        self._fitted = False

    def fit(self, data: pd.DataFrame) -> None:
        # Statistical baseline initializes on historical window
        self._fitted = True

    def predict(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        if data.empty or len(data) < self.min_history:
            return []

        anomalies = []
        for col in ["ph", "turbidity"]:
            if col not in data.columns:
                continue

            series = data[col].dropna()
            if len(series) < self.min_history:
                continue

            mean = series.mean()
            std = series.std()

            if std < 1e-4:
                continue  # No variance; avoid division by zero

            z_scores = (series - mean).abs() / std
            outliers = series[z_scores > self.threshold]

            for idx, val in outliers.items():
                anomalies.append({
                    "index": int(idx),
                    "parameter": col,
                    "measured_value": float(val),
                    "baseline_mean": float(mean),
                    "baseline_std": float(std),
                    "z_score": float(z_scores.loc[idx]),
                    "anomaly_type": f"STATISTICAL_SPIKE_{col.upper()}",
                })

        return anomalies


class IsolationForestDetector(BaseAnomalyDetector):
    """
    Unsupervised multivariate anomaly detector using Isolation Forests (scikit-learn).
    Prepared for Phase 2 training when sufficient continuous telemetry is acquired.
    """

    def __init__(self, contamination: float = 0.05):
        self.contamination = contamination
        self._model = None
        self._is_trained = False

    def fit(self, data: pd.DataFrame) -> None:
        from sklearn.ensemble import IsolationForest

        feature_cols = [c for c in ["ph", "turbidity", "ph_board_voltage", "turbidity_board_voltage"] if c in data.columns]
        clean_df = data[feature_cols].dropna()

        if len(clean_df) < 50:
            # Need at least 50 samples to build a meaningful Isolation Forest
            self._is_trained = False
            return

        self._model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
        )
        self._model.fit(clean_df)
        self._is_trained = True

    def predict(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        if not self._is_trained or self._model is None:
            return []

        feature_cols = [c for c in ["ph", "turbidity", "ph_board_voltage", "turbidity_board_voltage"] if c in data.columns]
        clean_df = data[feature_cols].dropna()
        if clean_df.empty:
            return []

        preds = self._model.predict(clean_df)
        scores = self._model.decision_function(clean_df)

        anomalies = []
        for i, (pred, score) in enumerate(zip(preds, scores)):
            if pred == -1:  # -1 represents an anomaly in IsolationForest
                row_idx = clean_df.index[i]
                anomalies.append({
                    "index": int(row_idx),
                    "anomaly_score": float(score),
                    "anomaly_type": "MULTIVARIATE_ISOLATION_ANOMALY",
                    "features": clean_df.iloc[i].to_dict(),
                })

        return anomalies
