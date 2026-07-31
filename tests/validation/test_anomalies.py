"""Tests for anomaly detection.

Every detector here is keyed by name, matching what the four views publish. Several of these
tests exist specifically to prove a detector still *fires*: when the views moved from codes to
names, five detectors kept their column guards and silently returned no warnings at all, so a
suite that only asserted "no false positives" passed while detection was dead.
"""

import pandas as pd
from validation.anomalies import (
    detect_yoy_anomalies,
    detect_release_drift,
    detect_missing_expected_data,
    detect_new_or_removed_entities,
    detect_row_count_change,
    detect_indicator_coverage_gaps,
    detect_sector_drift,
)


class TestDetectYoyAnomalies:
    def test_no_anomalies_for_stable_growth(self):
        # Consistent 5% growth should not flag
        df = pd.DataFrame(
            {
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
                "donor_name": ["Austria", "Belgium"],
                "value": [100, 200],
            }
        )
        previous = {"aggregates": {"by_donor": {"Austria": 100, "Belgium": 200}}}
        warnings = detect_release_drift(df, previous, "jun_2024", value_column="value")
        assert len(warnings) == 0

    def test_significant_drift(self):
        df = pd.DataFrame(
            {
                "donor_name": ["Austria", "Belgium"],
                "value": [100, 400],  # Belgium doubled
            }
        )
        previous = {"aggregates": {"by_donor": {"Austria": 100, "Belgium": 200}}}
        warnings = detect_release_drift(df, previous, "jun_2024", value_column="value")
        assert len(warnings) > 0
        assert any("Belgium" in w.message for w in warnings)

    def test_donor_that_vanished_reads_as_total_loss(self):
        # A donor in the baseline but absent from the data is -100%, not silently skipped.
        df = pd.DataFrame({"donor_name": ["Austria"], "value": [100]})
        previous = {"aggregates": {"by_donor": {"Austria": 100, "Belgium": 200}}}
        warnings = detect_release_drift(df, previous, "jun_2024", value_column="value")
        assert any("Belgium" in w.message and w.level == "high" for w in warnings)


class TestDetectMissingExpectedData:
    def test_no_missing_data(self):
        df = pd.DataFrame(
            {
                "donor_name": ["Austria", "Austria"],
                "year": [2023, 2024],
                "value": [100, 110],
            }
        )
        warnings = detect_missing_expected_data(
            df, major_donors=["Austria"], value_column="value"
        )
        assert len(warnings) == 0

    def test_missing_latest_year(self):
        df = pd.DataFrame(
            {
                "donor_name": ["Austria", "Belgium", "Belgium"],
                "year": [2023, 2023, 2024],  # Austria missing 2024
                "value": [100, 200, 210],
            }
        )
        warnings = detect_missing_expected_data(
            df, major_donors=["Austria", "Belgium"], value_column="value"
        )
        assert len(warnings) > 0
        assert any("Austria" in w.message for w in warnings)

    def test_all_zeros_in_latest_year(self):
        df = pd.DataFrame(
            {
                "donor_name": ["Austria", "Austria"],
                "year": [2023, 2024],
                "value": [100, 0],
            }
        )
        warnings = detect_missing_expected_data(
            df, major_donors=["Austria"], value_column="value"
        )
        assert any("zero" in w.message.lower() for w in warnings)


class TestDetectNewOrRemovedEntities:
    def test_new_donor(self):
        df = pd.DataFrame({"donor_name": ["Austria", "Belgium", "Denmark"]})
        previous = {"donors_present": ["Austria", "Belgium"]}
        warnings = detect_new_or_removed_entities(df, previous)
        assert any(
            "new" in w.message.lower() and "Denmark" in w.message for w in warnings
        )

    def test_removed_donor(self):
        df = pd.DataFrame({"donor_name": ["Austria"]})
        previous = {"donors_present": ["Austria", "Belgium"]}
        warnings = detect_new_or_removed_entities(df, previous)
        assert any(
            "removed" in w.message.lower() and "Belgium" in w.message for w in warnings
        )

    def test_removed_sector_is_high_priority(self):
        # A whole sector disappearing means spending stopped being classified, not just moved.
        df = pd.DataFrame({"sector_name": ["Health"]})
        previous = {"sectors_present": ["Health", "Education"]}
        warnings = detect_new_or_removed_entities(df, previous)
        assert any(
            w.level == "high" and "Education" in w.message for w in warnings
        )

    def test_removed_sub_sector_is_detected(self):
        df = pd.DataFrame({"sub_sector_name": ["Agriculture"]})
        previous = {"sub_sectors_present": ["Agriculture", "Elections"]}
        warnings = detect_new_or_removed_entities(df, previous)
        assert any("Elections" in w.message for w in warnings)

    def test_removed_indicator_is_detected(self):
        df = pd.DataFrame({"indicator_name": ["Bilateral"]})
        previous = {"indicators_present": ["Bilateral", "Imputed multilateral"]}
        warnings = detect_new_or_removed_entities(df, previous)
        assert any("Imputed multilateral" in w.message for w in warnings)


class TestDetectIndicatorCoverageGaps:
    def test_indicator_with_no_data_is_high(self):
        df = pd.DataFrame({"indicator_name": ["Bilateral"], "value": [100]})
        previous = {"indicators_present": ["Bilateral", "Imputed multilateral"]}
        warnings = detect_indicator_coverage_gaps(df, previous, value_column="value")
        assert any(
            w.level == "high" and "Imputed multilateral" in w.message for w in warnings
        )

    def test_indicator_all_zeros_is_flagged(self):
        df = pd.DataFrame(
            {"indicator_name": ["Bilateral", "Grants"], "value": [100, 0]}
        )
        previous = {"indicators_present": ["Bilateral", "Grants"]}
        warnings = detect_indicator_coverage_gaps(df, previous, value_column="value")
        assert any("Grants" in w.message and "zero" in w.message.lower() for w in warnings)

    def test_no_warnings_when_coverage_intact(self):
        df = pd.DataFrame(
            {"indicator_name": ["Bilateral", "Grants"], "value": [100, 50]}
        )
        previous = {"indicators_present": ["Bilateral", "Grants"]}
        assert detect_indicator_coverage_gaps(df, previous, value_column="value") == []


class TestDetectSectorDrift:
    def test_overall_sector_drift(self):
        df = pd.DataFrame({"sector_name": ["Health"], "value": [200]})
        previous = {"aggregates": {"by_sector": {"Health": 100}}}
        warnings = detect_sector_drift(df, previous, value_column="value")
        assert any("Health" in w.message for w in warnings)

    def test_donor_sector_drift_survives_a_flat_total(self):
        # France collapses and Germany grows by the same amount, so the sector total is
        # unchanged. Only the per-donor half can catch this.
        df = pd.DataFrame(
            {
                "donor_name": ["France", "Germany"],
                "sector_name": ["Health", "Health"],
                "value": [10, 190],
            }
        )
        previous = {
            "aggregates": {
                "by_sector": {"Health": 200},
                "by_donor_sector": {"France|Health": 100, "Germany|Health": 100},
            }
        }
        warnings = detect_sector_drift(df, previous, value_column="value")
        assert not any(
            "Sector 'Health'" in w.message for w in warnings
        ), "the sector total is flat, so it must not flag"
        assert any("France" in w.message for w in warnings)
        assert any("Germany" in w.message for w in warnings)


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
