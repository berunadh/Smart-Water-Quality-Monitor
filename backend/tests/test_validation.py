"""Unit tests for electrical invariant and sensor plausibility validation."""

import pytest
from app.services.validation_service import ValidationService


def test_valid_reading():
    is_valid, is_stale, notes = ValidationService.validate_reading(
        ph=7.35,
        turbidity=1.5,
        tds=None,
        ph_board_v=2.50,         # 2.50 * 0.40 = 1.00V ADC (safe)
        turbidity_board_v=4.20,  # 4.20 * 0.40 = 1.68V ADC (safe)
        health_code=0,
    )
    assert is_valid is True
    assert notes == "VALID"


def test_adc_over_range_hazard():
    # If board voltage is 7.835V (previous concerning software log):
    # 7.835 * 0.40 = 3.134V ADC -> Exceeds 3.05V safety limit!
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


def test_implausible_ph():
    is_valid, is_stale, notes = ValidationService.validate_reading(
        ph=15.2,  # Physical bounds 0 to 14
        turbidity=2.0,
        tds=None,
        ph_board_v=2.50,
        turbidity_board_v=4.00,
        health_code=0,
    )
    assert is_valid is False
    assert "PHYSICAL BOUND VIOLATION" in notes


def test_implausible_turbidity():
    is_valid, is_stale, notes = ValidationService.validate_reading(
        ph=7.2,
        turbidity=-3.0,  # Negative NTU is physically impossible
        tds=None,
        ph_board_v=2.50,
        turbidity_board_v=4.00,
        health_code=0,
    )
    assert is_valid is False
    assert "PHYSICAL BOUND VIOLATION" in notes


def test_missing_tds_vs_zero_tds():
    # Correct case: TDS is None (absent)
    is_valid_none, _, notes_none = ValidationService.validate_reading(
        ph=7.0, turbidity=1.0, tds=None, ph_board_v=2.5, turbidity_board_v=4.0, health_code=0
    )
    assert is_valid_none is True
    assert "WARNING" not in notes_none

    # Suspicious case: TDS is 0.0 (uninstalled sensor reported as 0)
    is_valid_zero, _, notes_zero = ValidationService.validate_reading(
        ph=7.0, turbidity=1.0, tds=0.0, ph_board_v=2.5, turbidity_board_v=4.0, health_code=0
    )
    assert is_valid_zero is True
    assert "WARNING: TDS reported as 0.0" in notes_zero
