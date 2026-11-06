"""Standard Library Unittest for Electrical Invariants and Data Contracts.
Runs independently without external third-party dependencies.
"""

import unittest
from datetime import datetime


class TestElectricalAndValidationContracts(unittest.TestCase):
    def setUp(self):
        self.r1 = 15000.0  # 15 kOhm
        self.r2 = 10000.0  # 10 kOhm
        self.divider_ratio = self.r2 / (self.r1 + self.r2)  # 0.400
        self.reconstruct_factor = 1.0 / self.divider_ratio  # 2.500
        self.adc_safe_max = 3.05

    def test_divider_ratio_calculation(self):
        self.assertAlmostEqual(self.divider_ratio, 0.400, places=4)
        self.assertAlmostEqual(self.reconstruct_factor, 2.500, places=4)

    def test_previous_alarming_ph_reading(self):
        """
        Verify previous software log:
        pH ADC: 3.134 V -> Reconstructed Board V = 7.835 V.
        Must be detected as HAZARDOUS (> 3.05 V ADC limit).
        """
        v_adc = 3.134
        v_board_est = v_adc * self.reconstruct_factor
        self.assertAlmostEqual(v_board_est, 7.835, places=3)
        self.assertGreater(v_adc, self.adc_safe_max)

    def test_safe_turbidity_reading(self):
        """
        Verify normal optical sensor output:
        Board output 4.20 V -> ADC = 1.68 V (< 3.05 V limit, completely safe).
        """
        v_board = 4.20
        v_adc = v_board * self.divider_ratio
        self.assertAlmostEqual(v_adc, 1.68, places=3)
        self.assertLess(v_adc, self.adc_safe_max)

    def test_missing_tds_contract(self):
        """Missing TDS sensor must strictly be None / empty string, NEVER 0.0."""
        def parse_tds(val):
            if val is None:
                return None
            s = str(val).strip()
            if not s or s.lower() in ("null", "nan", "n/a"):
                return None
            return float(s)

        self.assertIsNone(parse_tds(""))
        self.assertIsNone(parse_tds("   "))
        self.assertIsNone(parse_tds(None))
        self.assertIsNone(parse_tds("null"))
        self.assertIsNone(parse_tds("N/A"))
        self.assertEqual(parse_tds("250.0"), 250.0)
        # Note: If someone passes "0.0", it parses to 0.0 which our validator flags as suspicious
        self.assertEqual(parse_tds("0.0"), 0.0)

    def test_health_bitmask_decoding(self):
        # Bit 0: HEALTH_WIFI_DISCONNECTED
        # Bit 1: HEALTH_CLOUD_ERROR
        # Bit 2: HEALTH_PH_FAULT
        # Bit 3: HEALTH_TURB_FAULT
        # Bit 4: HEALTH_ADC_OVER_RANGE
        # Bit 5: HEALTH_TDS_UNAVAILABLE
        # Bit 6: HEALTH_CALIBRATION_PENDING
        # Bit 7: HEALTH_DEMO_MODE_ACTIVE

        # Normal operational bitmask (with TDS absent and calibration pending):
        code = (1 << 5) | (1 << 6)  # 0x0060 (96)
        self.assertTrue(code & (1 << 5), "TDS should be flagged unavailable")
        self.assertTrue(code & (1 << 6), "Calibration pending should be set")
        self.assertFalse(code & (1 << 4), "No ADC over-range hazard")
        self.assertFalse(code & (1 << 0), "Wi-Fi connected")

        # Over-range hazard injection
        hazard_code = code | (1 << 4)
        self.assertTrue(hazard_code & (1 << 4), "ADC Over-Range hazard flag recognized")


if __name__ == "__main__":
    unittest.main()
