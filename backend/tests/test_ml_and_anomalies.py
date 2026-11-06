"""Unit tests for ML anomaly detection, fault identification, and trend analysis."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from app.ml.anomaly_detector import RobustStatisticalDetector, IsolationForestDetector
from app.ml.fault_detector import SensorFaultDetector
from app.ml.trend_analyzer import TrendAnalyzer
from app.ml.trainer import ModelTrainer


def test_robust_statistical_detector_anomaly():
    """Detects sudden spikes in turbidity using rolling Median Absolute Deviation."""
    # 20 normal samples (~1.0 NTU), then 1 large spike (12.0 NTU)
    now = datetime.utcnow()
    timestamps = [now + timedelta(minutes=i) for i in range(21)]
    turbidity = [1.0 + (i % 2) * 0.05 for i in range(20)] + [12.5]
    ph = [7.35 for _ in range(21)]

    df = pd.DataFrame({
        "timestamp": timestamps,
        "ph": ph,
        "turbidity": turbidity,
    })

    detector = RobustStatisticalDetector(z_threshold=3.0)
    anomalies = detector.predict(df)

    assert len(anomalies) >= 1
    found_spike = any(a.parameter == "turbidity" and a.measured_value > 10.0 for a in anomalies)
    assert found_spike is True


def test_isolation_forest_detector_fit_and_predict():
    """Trains Isolation Forest on synthetic data and tests anomaly prediction."""
    train_df, test_df = ModelTrainer.generate_synthetic_training_data(samples=200)

    detector = IsolationForestDetector(contamination=0.08)
    fit_res = detector.fit(train_df, is_synthetic=True)
    assert fit_res["status"] == "SUCCESS"
    assert detector._is_trained is True

    anomalies = detector.predict(test_df)
    assert isinstance(anomalies, list)
    # The synthetic test set has 10 known injected anomalies
    assert len(anomalies) > 0
    assert detector.metadata["trained_on_synthetic_data"] is True


def test_sensor_fault_detector_stuck_value():
    """Identifies dead/stuck sensor output with zero analog variance."""
    now = datetime.utcnow()
    timestamps = [now + timedelta(minutes=i) for i in range(10)]
    # 10 completely identical readings (0.000 variance)
    frozen_ph_v = [2.51234] * 10
    turb_v = [4.10 + (i * 0.02) for i in range(10)]

    df = pd.DataFrame({
        "timestamp": timestamps,
        "ph_voltage": frozen_ph_v,
        "turbidity_voltage": turb_v,
    })

    faults = SensorFaultDetector.analyze_faults(df)
    assert len(faults) >= 1
    assert any(f.anomaly_type == "HARDWARE_STUCK_VALUE" for f in faults)


def test_sensor_fault_detector_disconnected_probe():
    """Identifies disconnected probe outputting ~0.0V."""
    df = pd.DataFrame({
        "timestamp": [datetime.utcnow()],
        "ph_voltage": [0.02],  # ~0V open circuit
        "turbidity_voltage": [4.15],
    })

    faults = SensorFaultDetector.analyze_faults(df)
    assert len(faults) >= 1
    assert any(f.anomaly_type == "PROBE_DISCONNECTED" for f in faults)


def test_trend_analyzer_increasing_turbidity():
    """Calculates linear slope and identifies an increasing turbidity trend."""
    now = datetime.utcnow()
    # Turbidity rises by 0.5 NTU every 10 minutes (3.0 NTU per hour)
    t = [now + timedelta(minutes=i * 10) for i in range(12)]
    turb = [1.0 + (i * 0.5) for i in range(12)]

    df = pd.DataFrame({
        "timestamp": t,
        "turbidity": turb,
        "ph": [7.35] * 12,
    })

    trend_resp = TrendAnalyzer.evaluate_water_trends(df)
    assert trend_resp.turbidity_drift.trend_direction == "INCREASING"
    assert trend_resp.turbidity_drift.slope_per_hour > 2.0
    assert trend_resp.turbidity_drift.r_squared > 0.90
