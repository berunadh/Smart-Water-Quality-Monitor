"""Integration tests for all FastAPI REST endpoints."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "operating_mode" in data
    assert "cloud_connectivity" in data


def test_system_status():
    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert "overall_status" in data
    assert "electrical_safe" in data
    assert "tds_installed" in data
    assert data["tds_installed"] is False  # TDS absent in Phase 2


def test_readings_latest():
    res = client.get("/api/readings/latest")
    assert res.status_code == 200
    data = res.json()
    if data:
        assert "ph" in data
        assert "turbidity" in data
        assert data["tds"] is None  # TDS must be null
        assert "operating_mode" in data
        assert "data_source" in data


def test_readings_history():
    res = client.get("/api/readings/history?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) <= 10


def test_readings_statistics():
    res = client.get("/api/readings/statistics?hours=24")
    assert res.status_code == 200
    data = res.json()
    assert "count" in data
    assert "ph_mean" in data


def test_alerts_summary():
    res = client.get("/api/alerts")
    assert res.status_code == 200
    data = res.json()
    assert "total_active" in data
    assert "recent_alerts" in data


def test_ml_anomalies_endpoint():
    res = client.get("/api/ml/anomalies?limit=30")
    assert res.status_code == 200
    data = res.json()
    assert "anomalies" in data
    assert "analyzed_samples" in data


def test_ml_trends_endpoint():
    res = client.get("/api/ml/trends?limit=30")
    assert res.status_code == 200
    data = res.json()
    assert "ph_drift" in data
    assert "turbidity_drift" in data


def test_ml_summary_endpoint():
    res = client.get("/api/ml/summary")
    assert res.status_code == 200
    data = res.json()
    assert "insights" in data
    assert "dominant_trend" in data


def test_chat_endpoint():
    payload = {"message": "What is the current water status?"}
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "response" in data
    assert "source" in data
    assert "context_used" in data


def test_demo_inject_endpoint():
    res = client.post("/api/demo/inject/warning")
    assert res.status_code == 200
    data = res.json()
    assert data["alert_severity"] == 1
    assert data["tds"] is None
