"""Model training, synthetic benchmarking, and retraining workflow."""

import os
from typing import Dict, Any, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.water_reading import WaterReadingModel
from app.ml.anomaly_detector import IsolationForestDetector


class ModelTrainer:
    """
    Manages Scikit-learn model training, synthetic benchmarking,
    and retraining workflows on real accumulated historical telemetry.
    """

    @classmethod
    def generate_synthetic_training_data(cls, samples: int = 500) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Synthesizes a clean baseline dataset representing normal municipal water,
        plus an independent evaluation split with injected anomalies.
        All synthetic data is explicitly labelled.
        """
        np.random.seed(42)
        base_time = datetime.utcnow() - timedelta(minutes=samples * 2)

        # Baseline Clean Tap Water Simulation:
        # pH: mean 7.35, std 0.08
        # Turbidity: mean 0.85 NTU, std 0.15
        # pH Vboard: 2.50V, Turb Vboard: 4.20V
        ph_clean = np.random.normal(loc=7.35, scale=0.08, size=samples)
        turb_clean = np.clip(np.random.normal(loc=0.85, scale=0.15, size=samples), 0.1, 5.0)
        ph_v_clean = 2.50 + (ph_clean - 7.00) * 0.18 + np.random.normal(0, 0.01, size=samples)
        turb_v_clean = 4.25 - (turb_clean * 0.08) + np.random.normal(0, 0.01, size=samples)

        train_df = pd.DataFrame({
            "timestamp": [base_time + timedelta(minutes=i * 2) for i in range(samples)],
            "ph": ph_clean,
            "turbidity": turb_clean,
            "ph_voltage": ph_v_clean,
            "turbidity_voltage": turb_v_clean,
            "is_synthetic": True,
        })

        # Generate Test Evaluation Split (100 samples with 10 injected anomalies)
        test_samples = 100
        ph_test = np.random.normal(loc=7.35, scale=0.08, size=test_samples)
        turb_test = np.clip(np.random.normal(loc=0.85, scale=0.15, size=test_samples), 0.1, 5.0)
        labels = np.zeros(test_samples, dtype=int)  # 0 = normal, 1 = anomaly

        # Inject 10 known anomalies
        # Anomaly 1: Turbidity spike (>10 NTU)
        turb_test[15:20] = [12.5, 14.2, 16.8, 11.0, 9.5]
        labels[15:20] = 1

        # Anomaly 2: Acidic drift
        ph_test[60:65] = [5.8, 5.4, 5.1, 5.6, 6.0]
        labels[60:65] = 1

        ph_v_test = 2.50 + (ph_test - 7.00) * 0.18
        turb_v_test = 4.25 - (turb_test * 0.08)

        test_df = pd.DataFrame({
            "timestamp": [datetime.utcnow() - timedelta(minutes=(test_samples - i) * 2) for i in range(test_samples)],
            "ph": ph_test,
            "turbidity": turb_test,
            "ph_voltage": ph_v_test,
            "turbidity_voltage": turb_v_test,
            "true_anomaly": labels,
            "is_synthetic": True,
        })

        return train_df, test_df

    @classmethod
    def train_baseline_model(cls) -> Dict[str, Any]:
        """
        Trains the initial Isolation Forest on synthetic baseline data,
        evaluates performance on a synthetic validation split, and persists the model.
        """
        train_df, test_df = cls.generate_synthetic_training_data(samples=600)
        detector = IsolationForestDetector(contamination=settings.ML_CONTAMINATION_RATE)
        fit_result = detector.fit(train_df, is_synthetic=True)

        if fit_result.get("status") != "SUCCESS":
            return fit_result

        # Validation on test split
        anomalies = detector.predict(test_df)
        detected_indices = {a.measured_value for a in anomalies}  # match via score/index

        # Add benchmark evaluation to metadata
        eval_meta = {
            "evaluation_note": "Evaluated against controlled synthetic benchmark with 10 injected anomalies.",
            "synthetic_test_samples": len(test_df),
            "injected_anomalies_count": int(test_df["true_anomaly"].sum()),
            "detected_anomalies_count": len(anomalies),
        }
        detector.metadata.update(eval_meta)
        detector.save()

        return {
            "status": "SUCCESS",
            "model_metadata": detector.metadata,
        }

    @classmethod
    def retrain_from_database(cls, db: Session) -> Dict[str, Any]:
        """
        Retrains the Isolation Forest model using actual accumulated telemetry from SQLite.
        Requires at least 50 valid historical records.
        """
        readings = (
            db.query(WaterReadingModel)
            .filter(WaterReadingModel.is_valid == True)
            .order_by(WaterReadingModel.timestamp.desc())
            .limit(2000)
            .all()
        )

        if len(readings) < 50:
            return {
                "status": "INSUFFICIENT_REAL_DATA",
                "message": f"Retraining requires at least 50 valid records. Database currently has {len(readings)}.",
            }

        data = [
            {
                "timestamp": r.timestamp,
                "ph": r.ph,
                "turbidity": r.turbidity,
                "ph_voltage": r.ph_voltage,
                "turbidity_voltage": r.turbidity_voltage,
            }
            for r in readings
        ]
        df = pd.DataFrame(data)

        detector = IsolationForestDetector(contamination=settings.ML_CONTAMINATION_RATE)
        # Check whether the data is real or simulated
        is_synthetic = any(r.operating_mode == "demo" or r.data_source == "simulated" for r in readings)
        result = detector.fit(df, is_synthetic=is_synthetic)
        return result
