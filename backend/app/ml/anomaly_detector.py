"""Machine learning and statistical anomaly detection architectures."""

import os
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np
import pandas as pd
import joblib

from app.core.config import settings
from app.core.logging import logger
from app.schemas.ml import AnomalyItem


class BaseAnomalyDetector(ABC):
    @abstractmethod
    def fit(self, data: pd.DataFrame) -> None:
        pass

    @abstractmethod
    def predict(self, data: pd.DataFrame) -> List[AnomalyItem]:
        pass


class RobustStatisticalDetector(BaseAnomalyDetector):
    """
    Robust Statistical Anomaly Detector using Rolling Median,
    Median Absolute Deviation (MAD), and dynamic Z-Scores.
    
    Ideal for water telemetry where sudden contamination events or line noise
    spike above recent moving baselines.
    """

    def __init__(self, z_threshold: float = 3.0, min_history: int = 5):
        self.z_threshold = z_threshold
        self.min_history = min_history

    def fit(self, data: pd.DataFrame) -> None:
        # Non-parametric statistical detector adapts dynamically to window
        pass

    def predict(self, data: pd.DataFrame) -> List[AnomalyItem]:
        if data.empty or len(data) < self.min_history:
            return []

        anomalies: List[AnomalyItem] = []

        for col in ["ph", "turbidity"]:
            if col not in data.columns:
                continue

            series = data[col].dropna()
            if len(series) < self.min_history:
                continue

            median = float(series.median())
            # Median Absolute Deviation (MAD)
            mad = float((series - median).abs().median())
            # Normal consistency factor (1.4826 * MAD approximates std)
            robust_scale = 1.4826 * mad if mad > 1e-4 else float(series.std())

            if robust_scale < 1e-4:
                continue  # Constant or dead flat signal; handled by FaultDetector

            z_scores = (series - median).abs() / robust_scale
            outlier_mask = z_scores > self.z_threshold

            for idx in series[outlier_mask].index:
                val = float(series.loc[idx])
                score = float(z_scores.loc[idx])
                ts = data.loc[idx, "timestamp"] if "timestamp" in data.columns else None
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)

                if col == "ph":
                    desc = f"pH level ({val:.2f}) diverged significantly from moving median ({median:.2f}) by {score:.1f}σ."
                else:
                    desc = f"Turbidity reading ({val:.1f} NTU) spiked sharply above moving median ({median:.1f} NTU) by {score:.1f}σ."

                anomalies.append(
                    AnomalyItem(
                        timestamp=ts,
                        parameter=col,
                        measured_value=val,
                        baseline_mean=median,
                        baseline_std=robust_scale,
                        anomaly_score=round(score, 2),
                        detector_type="statistical_mad",
                        anomaly_type=f"STATISTICAL_SPIKE_{col.upper()}",
                        human_explanation=desc,
                        category="STATISTICAL_ANOMALY",
                    )
                )

        return anomalies


# Alias for backward compatibility
ZScoreAnomalyDetector = RobustStatisticalDetector


class IsolationForestDetector(BaseAnomalyDetector):
    """
    Unsupervised multivariate anomaly detector using Scikit-learn Isolation Forests.
    Detects correlated anomalies across pH, turbidity, and sensor board voltages.
    """

    FEATURE_COLS = ["ph", "turbidity", "ph_voltage", "turbidity_voltage"]

    def __init__(self, contamination: float = 0.05, model_path: Optional[str] = None):
        self.contamination = contamination
        self.model_path = model_path or os.path.join(settings.ML_MODEL_DIR, "isolation_forest.joblib")
        self.meta_path = self.model_path.replace(".joblib", "_meta.json")
        self._model = None
        self._is_trained = False
        self.metadata: Dict[str, Any] = {}

        # Auto-load existing persisted model if present
        self.load()

    def fit(self, data: pd.DataFrame, is_synthetic: bool = True) -> Dict[str, Any]:
        from sklearn.ensemble import IsolationForest

        available_cols = [c for c in self.FEATURE_COLS if c in data.columns]
        clean_df = data[available_cols].dropna()

        if len(clean_df) < 20:
            logger.warning("[ML] Insufficient data samples (<20) to fit Isolation Forest.")
            return {"status": "FAILED", "reason": "Insufficient samples"}

        self._model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
            max_samples="auto",
        )
        self._model.fit(clean_df)
        self._is_trained = True

        self.metadata = {
            "model_type": "IsolationForest",
            "version": "1.0.0",
            "features": available_cols,
            "trained_at": datetime.utcnow().isoformat(),
            "sample_count": len(clean_df),
            "contamination": self.contamination,
            "trained_on_synthetic_data": is_synthetic,
            "validation_note": "Trained on controlled baseline. Real-world validation pending live sensor telemetry.",
        }

        self.save()
        logger.info(f"[ML] Isolation Forest trained successfully on {len(clean_df)} records (synthetic: {is_synthetic}).")
        return {"status": "SUCCESS", "metadata": self.metadata}

    def predict(self, data: pd.DataFrame) -> List[AnomalyItem]:
        if not self._is_trained or self._model is None:
            return []

        available_cols = [c for c in self.FEATURE_COLS if c in data.columns]
        clean_df = data[available_cols].dropna()
        if clean_df.empty:
            return []

        preds = self._model.predict(clean_df)
        scores = self._model.decision_function(clean_df)

        anomalies: List[AnomalyItem] = []
        for i, (pred, score) in enumerate(zip(preds, scores)):
            if pred == -1:  # -1 signifies an anomaly in IsolationForest
                row_idx = clean_df.index[i]
                row = clean_df.iloc[i]
                ts = data.loc[row_idx, "timestamp"] if "timestamp" in data.columns else None
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)

                norm_score = round(float(-score), 3)  # Invert so higher = more anomalous
                desc = (
                    f"Multivariate outlier detected (score: {norm_score}). "
                    f"Parameters: pH={row.get('ph', 'N/A')}, Turbidity={row.get('turbidity', 'N/A')} NTU, "
                    f"Voltages: pH={row.get('ph_voltage', 'N/A')}V, Turb={row.get('turbidity_voltage', 'N/A')}V."
                )

                anomalies.append(
                    AnomalyItem(
                        timestamp=ts,
                        parameter="multivariate",
                        measured_value=float(row.get("turbidity", 0.0)),
                        baseline_mean=None,
                        baseline_std=None,
                        anomaly_score=norm_score,
                        detector_type="isolation_forest",
                        anomaly_type="MULTIVARIATE_ISOLATION_ANOMALY",
                        human_explanation=desc,
                        category="ML_PREDICTION",
                    )
                )

        return anomalies

    def save(self) -> None:
        if self._model is not None:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            joblib.dump(self._model, self.model_path)
            with open(self.meta_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2)

    def load(self) -> bool:
        if os.path.exists(self.model_path) and os.path.exists(self.meta_path):
            try:
                self._model = joblib.load(self.model_path)
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                self._is_trained = True
                logger.info(f"[ML] Loaded persisted Isolation Forest model ({self.model_path}).")
                return True
            except Exception as exc:
                logger.warning(f"[ML] Failed loading persisted model: {exc}")
                self._is_trained = False
                return False
        return False
