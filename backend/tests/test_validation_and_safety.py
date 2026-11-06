"""Unit tests for electrical invariant validation, physical plausibility bounds, and staleness."""

import pytest
from datetime import datetime, timedelta
from app.services.validation_service import ValidationService


def test_electrical_over_range_hazard():
    """
    If board output voltage exceeds safe divider threshold,
    ADC pin voltage exceeds 3.05V, which must be rejected as an electrical hazard.
    """
    # 7.835V * 0.40 = 3.134V (Dangerously exceeds 3.05V)
    is_valid, is_stale, notes = ValidationService.validate_reading(
        ph=7.0,
        turbidity=1.0,
        tds=None,
        ph_board_v=7.835,
        turbidity_board_v=3.80,
        health_code=0,
    )
    assert is_valid is False
    assert "HAZARD" in notes
    assert "exceeds 3.05V safety limit" in notes


def test_staleness_detection():
    """Readings older than 5 minutes (300s) must be flagged as stale."""
    old_time = datetime.utcnow() - timedelta(minutes=10)
    is_valid, is_stale, notes = ValidationService.validate_reading(
        ph=7.3,
        turbidity=1.1,
        tds=None,
        ph_board_v=2.50,
        turbidity_board_v=4.20,
        health_code=0,
        timestamp=old_time,
    )
    assert is_valid is True
    assert is_stale is True
    assert "STALE" in notes


def test_suspicious_zero_tds_warning():
    """A TDS value of 0.0 must raise a warning note because absent sensors should be null."""
    is_valid, is_stale, notes = ValidationService.validate_reading(
        ph=7.2,
        turbidity=1.0,
        tds=0.0,
        ph_board_v=2.50,
        turbidity_board_v=4.20,
        health_code=0,
    )
    assert is_valid is True
    assert "WARNING: TDS reported as 0.0" in notes


def test_physical_bounds_violation():
    """Negative turbidity and pH outside [0, 14] must be rejected."""
    # Negative turbidity
    is_valid, _, notes = ValidationService.validate_reading(
        ph=7.0, turbidity=-2.5, tds=None, ph_board_v=2.5, turbidity_board_v=4.0, health_code=0
    )
    assert is_valid is False
    assert "PHYSICAL BOUND VIOLATION" in notes

    # Out of range pH
    is_valid, _, notes = ValidationService.validate_reading(
        ph=16.8, turbidity=1.0, tds=None, ph_board_v=2.5, turbidity_board_v=4.0, health_code=0
    )
    assert is_valid is False
    assert "PHYSICAL BOUND VIOLATION" in notes
