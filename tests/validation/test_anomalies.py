"""Tests for anomaly detection."""

import pandas as pd
import pytest
from validation.anomalies import (
    detect_yoy_anomalies,
    detect_release_drift,
    detect_missing_expected_data,
    detect_new_or_removed_codes,
    detect_row_count_change,
)
from validation.models import Warning


class TestDetectYoyAnomalies:
    def test_no_anomalies_for_stable_growth(self):
        # Consistent 5% growth should not flag
        df = pd.DataFrame(
            {
                "donor_code": [1] * 5,
                "donor_name": ["Austria"] * 5,
                "year": [2019, 2020, 2021, 2022, 2023],
                "value": [100, 105, 110, 115, 120],  # ~5% growth
            }
        )
        warnings = detect_yoy_anomalies(df, current_year=2023, value_column="value")
        high_warnings = [w for w in warnings if w.level == "high"]
        assert len(high_warnings) == 0

    def test_flags_large_spike(self):
        # Sudden 50% jump should flag
        df = pd.DataFrame(
            {
                "donor_code": [1] * 5,
                "donor_name": ["Austria"] * 5,
                "year": [2019, 2020, 2021, 2022, 2023],
                "value": [100, 105, 110, 115, 175],  # 50% jump in last year
            }
        )
        warnings = detect_yoy_anomalies(df, current_year=2023, value_column="value")
        assert len(warnings) > 0
        assert any("Austria" in w.message for w in warnings)


class TestDetectReleaseDrift:
    def test_no_drift(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 2],
                "value": [100, 200],
            }
        )
        previous = {"aggregates": {"by_donor": {"1": 100, "2": 200}}}
        warnings = detect_release_drift(df, previous, "jun_2024", value_column="value")
        assert len(warnings) == 0

    def test_significant_drift(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 2],
                "donor_name": ["Austria", "Belgium"],
                "value": [100, 400],  # Belgium doubled
            }
        )
        previous = {"aggregates": {"by_donor": {"1": 100, "2": 200}}}
        warnings = detect_release_drift(df, previous, "jun_2024", value_column="value")
        assert len(warnings) > 0
        assert any("Belgium" in w.message or "2" in w.message for w in warnings)


class TestDetectMissingExpectedData:
    def test_no_missing_data(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 1],
                "donor_name": ["Austria", "Austria"],
                "year": [2023, 2024],
                "value": [100, 110],
            }
        )
        warnings = detect_missing_expected_data(
            df, major_donors={1: "Austria"}, value_column="value"
        )
        assert len(warnings) == 0

    def test_missing_latest_year(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 2, 2],
                "donor_name": ["Austria", "Belgium", "Belgium"],
                "year": [2023, 2023, 2024],  # Austria missing 2024
                "value": [100, 200, 210],
            }
        )
        warnings = detect_missing_expected_data(
            df, major_donors={1: "Austria", 2: "Belgium"}, value_column="value"
        )
        assert len(warnings) > 0
        assert any("Austria" in w.message for w in warnings)


class TestDetectNewOrRemovedCodes:
    def test_new_donor(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 2, 3],  # 3 is new
            }
        )
        previous = {"donors_present": [1, 2]}
        warnings = detect_new_or_removed_codes(df, previous)
        assert any(
            "new" in w.message.lower() and "3" in str(w.message) for w in warnings
        )

    def test_removed_donor(self):
        df = pd.DataFrame(
            {
                "donor_code": [1],  # 2 is gone
            }
        )
        previous = {"donors_present": [1, 2]}
        warnings = detect_new_or_removed_codes(df, previous)
        assert any(
            "removed" in w.message.lower() and "2" in str(w.message) for w in warnings
        )


class TestDetectRowCountChange:
    def test_small_change_no_warning(self):
        warnings = detect_row_count_change(
            current_count=1050,
            previous_count=1000,
            dataset="test",
            threshold=0.10,
        )
        assert len(warnings) == 0

    def test_large_decrease_warns(self):
        warnings = detect_row_count_change(
            current_count=700,
            previous_count=1000,
            dataset="test",
            threshold=0.10,
        )
        assert len(warnings) > 0
        assert any("-30" in w.message or "30%" in w.message for w in warnings)
