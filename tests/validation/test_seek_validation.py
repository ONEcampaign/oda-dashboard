"""Tests for SEEK-style sector validation."""

import pandas as pd
import pytest
from validation.config import (
    SEEK_HEALTH_PURPOSE_CODES,
    SEEK_AGRICULTURE_PURPOSE_CODES,
)
from validation.seek_data import (
    filter_by_purpose_codes,
    aggregate_by_donor,
    get_latest_year_data,
    get_donor_names,
    compute_sector_aggregates,
)
from validation.seek_anomalies import (
    detect_seek_donor_drift,
    detect_seek_missing_donors,
    detect_seek_new_donors,
    run_seek_validation,
)
from validation.seek_manifest import (
    update_seek_manifest,
    get_previous_seek_release,
)


class TestFilterByPurposeCodes:
    def test_filters_health_codes(self):
        df = pd.DataFrame(
            {
                "purpose_code": [12110, 12220, 31110, 43040, 99999],
                "value": [100, 200, 300, 400, 500],
            }
        )
        # 12110 and 12220 are health codes
        filtered = filter_by_purpose_codes(df, SEEK_HEALTH_PURPOSE_CODES)
        assert len(filtered) == 2
        assert filtered["value"].sum() == 300

    def test_filters_agriculture_codes(self):
        df = pd.DataFrame(
            {
                "purpose_code": [12110, 31110, 31120, 43040, 99999],
                "value": [100, 200, 300, 400, 500],
            }
        )
        # 31110, 31120, 43040 are agriculture codes
        filtered = filter_by_purpose_codes(df, SEEK_AGRICULTURE_PURPOSE_CODES)
        assert len(filtered) == 3
        assert filtered["value"].sum() == 900

    def test_empty_result_when_no_matches(self):
        df = pd.DataFrame(
            {
                "purpose_code": [99999, 88888],
                "value": [100, 200],
            }
        )
        filtered = filter_by_purpose_codes(df, SEEK_HEALTH_PURPOSE_CODES)
        assert len(filtered) == 0


class TestAggregateByDonor:
    def test_aggregates_correctly(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 1, 2, 2, 2],
                "value": [100, 150, 200, 250, 300],
            }
        )
        result = aggregate_by_donor(df)
        assert result[1] == 250
        assert result[2] == 750


class TestGetLatestYearData:
    def test_returns_latest_year(self):
        df = pd.DataFrame(
            {
                "year": [2021, 2022, 2023, 2023],
                "value": [100, 200, 300, 400],
            }
        )
        result = get_latest_year_data(df)
        assert len(result) == 2
        assert all(result["year"] == 2023)

    def test_handles_empty_dataframe(self):
        df = pd.DataFrame({"year": [], "value": []})
        result = get_latest_year_data(df)
        assert len(result) == 0


class TestGetDonorNames:
    def test_extracts_names(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 1, 2],
                "donor_name": ["Austria", "Austria", "Belgium"],
            }
        )
        result = get_donor_names(df)
        assert result[1] == "Austria"
        assert result[2] == "Belgium"

    def test_handles_missing_column(self):
        df = pd.DataFrame({"donor_code": [1, 2]})
        result = get_donor_names(df)
        assert result == {}


class TestComputeSectorAggregates:
    def test_computes_all_aggregates(self):
        df = pd.DataFrame(
            {
                "year": [2023, 2023, 2023, 2023],
                "donor_code": [1, 1, 2, 2],
                "purpose_code": [12110, 31110, 12110, 43040],  # health, ag, health, ag
                "value": [100, 200, 300, 400],
            }
        )
        result = compute_sector_aggregates(df)

        assert result["latest_year"] == 2023
        # Total: donor 1 = 300, donor 2 = 700
        assert result["by_donor_total"][1] == 300
        assert result["by_donor_total"][2] == 700
        # Health: donor 1 = 100, donor 2 = 300
        assert result["by_donor_health"][1] == 100
        assert result["by_donor_health"][2] == 300
        # Agriculture: donor 1 = 200, donor 2 = 400
        assert result["by_donor_agriculture"][1] == 200
        assert result["by_donor_agriculture"][2] == 400


class TestDetectSeekDonorDrift:
    def test_no_drift(self):
        current = {1: 100, 2: 200, 3: 300}
        previous = {1: 100, 2: 200, 3: 300}
        warnings = detect_seek_donor_drift(
            current, previous, "total", {1: "Austria", 2: "Belgium", 3: "Denmark"}
        )
        assert len(warnings) == 0

    def test_significant_drift_flagged(self):
        # One donor with much larger change than others
        current = {1: 100, 2: 400, 3: 300}  # Belgium doubled
        previous = {1: 100, 2: 200, 3: 300}
        warnings = detect_seek_donor_drift(
            current, previous, "health", {1: "Austria", 2: "Belgium", 3: "Denmark"}
        )
        assert len(warnings) > 0
        assert any("Belgium" in w.message for w in warnings)
        assert any("health" in w.message.lower() for w in warnings)

    def test_empty_previous_no_warnings(self):
        current = {1: 100, 2: 200}
        previous = {}
        warnings = detect_seek_donor_drift(
            current, previous, "total", {1: "Austria", 2: "Belgium"}
        )
        assert len(warnings) == 0

    def test_uses_pct_fallback_for_few_donors(self):
        # Only one donor - can't compute meaningful Z-score
        current = {1: 200}
        previous = {1: 100}  # 100% increase
        warnings = detect_seek_donor_drift(
            current, previous, "agriculture", {1: "Austria"}
        )
        assert len(warnings) > 0
        assert any("Austria" in w.message for w in warnings)


class TestDetectSeekMissingDonors:
    def test_no_missing_donors(self):
        current = {1: 100, 2: 200}
        previous = {1: 100, 2: 200}
        warnings = detect_seek_missing_donors(
            current,
            previous,
            "total",
            {1: "Austria", 2: "Belgium"},
            critical_donors=[1, 2],
        )
        assert len(warnings) == 0

    def test_missing_critical_donor_flagged(self):
        current = {1: 100}  # donor 2 missing
        previous = {1: 100, 2: 200}
        warnings = detect_seek_missing_donors(
            current,
            previous,
            "health",
            {1: "Austria", 2: "Belgium"},
            critical_donors=[1, 2],
        )
        assert len(warnings) == 1
        assert "Belgium" in warnings[0].message
        assert warnings[0].level == "high"

    def test_non_critical_donor_missing_not_flagged(self):
        current = {1: 100}  # donor 2 missing but not critical
        previous = {1: 100, 2: 200}
        warnings = detect_seek_missing_donors(
            current,
            previous,
            "total",
            {1: "Austria", 2: "Belgium"},
            critical_donors=[1],  # Only 1 is critical
        )
        assert len(warnings) == 0


class TestDetectSeekNewDonors:
    def test_new_donor_flagged(self):
        current = {1: 100, 2: 200, 3: 300}  # 3 is new
        previous = {1: 100, 2: 200}
        warnings = detect_seek_new_donors(
            current,
            previous,
            "total",
            {1: "Austria", 2: "Belgium", 3: "Denmark"},
        )
        assert len(warnings) == 1
        assert warnings[0].level == "info"
        assert "Denmark" in warnings[0].message

    def test_no_new_donors(self):
        current = {1: 100, 2: 200}
        previous = {1: 100, 2: 200}
        warnings = detect_seek_new_donors(
            current,
            previous,
            "total",
            {1: "Austria", 2: "Belgium"},
        )
        assert len(warnings) == 0


class TestRunSeekValidation:
    def test_runs_all_checks(self):
        df = pd.DataFrame(
            {
                "year": [2023, 2023, 2023, 2023],
                "donor_code": [1, 1, 2, 2],
                "donor_name": ["Austria", "Austria", "Belgium", "Belgium"],
                "purpose_code": [12110, 31110, 12110, 43040],
                "value": [100, 200, 600, 400],  # Belgium much higher
            }
        )
        previous_release = {
            "by_donor_total": {"1": 300, "2": 500},
            "by_donor_health": {"1": 100, "2": 300},
            "by_donor_agriculture": {"1": 200, "2": 200},
        }
        warnings = run_seek_validation(
            df=df,
            previous_release=previous_release,
            donor_names={1: "Austria", 2: "Belgium"},
        )
        # Should have some warnings due to Belgium's doubled agriculture
        assert len(warnings) > 0


class TestSeekManifest:
    def test_update_manifest_creates_structure(self):
        df = pd.DataFrame(
            {
                "year": [2023, 2023],
                "donor_code": [1, 2],
                "purpose_code": [12110, 31110],
                "value": [100, 200],
            }
        )
        manifest = {}
        manifest = update_seek_manifest(manifest, "dec_2024", df)

        assert manifest["dataset"] == "seek_sectors_validation"
        assert "dec_2024" in manifest["releases"]
        assert manifest["releases"]["dec_2024"]["latest_year"] == 2023
        assert "1" in manifest["releases"]["dec_2024"]["by_donor_total"]
        assert "1" in manifest["releases"]["dec_2024"]["by_donor_health"]
        assert "2" in manifest["releases"]["dec_2024"]["by_donor_agriculture"]

    def test_get_previous_release_returns_most_recent_by_timestamp(self):
        # Should return the most recent release by computed_at timestamp
        manifest = {
            "releases": {
                "april_2025": {
                    "computed_at": "2025-04-15T10:00:00",
                    "latest_year": 2024,
                },
                "dec_2024": {
                    "computed_at": "2024-12-15T10:00:00",
                    "latest_year": 2023,
                },
            }
        }
        previous = get_previous_seek_release(manifest)
        # Should get april_2025 (most recent by timestamp)
        assert previous["latest_year"] == 2024

    def test_get_previous_release_falls_back_to_name_sort(self):
        # When no computed_at, falls back to release name sorting
        manifest = {
            "releases": {
                "2025-04": {"latest_year": 2024},
                "2024-12": {"latest_year": 2023},
            }
        }
        previous = get_previous_seek_release(manifest)
        # Should get 2025-04 (alphabetically last when sorted in reverse)
        assert previous["latest_year"] == 2024

    def test_get_previous_release_empty_manifest(self):
        manifest = {"releases": {}}
        previous = get_previous_seek_release(manifest)
        assert previous == {}
