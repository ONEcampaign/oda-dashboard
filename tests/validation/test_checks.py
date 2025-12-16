"""Tests for hard gate validation checks."""

import pandas as pd
import pytest
from validation.checks import (
    check_schema,
    check_not_empty,
    check_no_duplicate_keys,
    check_value_columns_populated,
    check_value_bounds,
    check_name_mappings_complete,
    check_critical_dimensions,
)


class TestCheckSchema:
    def test_valid_schema(self):
        df = pd.DataFrame({
            "year": [2020, 2021],
            "donor_code": [1, 2],
            "value": [100, 200],
        })
        expected = {
            "columns": ["year", "donor_code", "value"],
            "dtypes": {"year": "int64", "donor_code": "int64", "value": "int64"},
        }
        result = check_schema(df, expected)
        assert result.passed is True

    def test_missing_column(self):
        df = pd.DataFrame({
            "year": [2020, 2021],
            "value": [100, 200],
        })
        expected = {
            "columns": ["year", "donor_code", "value"],
            "dtypes": {},
        }
        result = check_schema(df, expected)
        assert result.passed is False
        assert any("donor_code" in e for e in result.errors)

    def test_type_mismatch_fails(self):
        df = pd.DataFrame({
            "year": ["2020", "2021"],  # String instead of int
            "donor_code": [1, 2],
        })
        expected = {
            "columns": ["year", "donor_code"],
            "dtypes": {"year": "int64", "donor_code": "int64"},
        }
        result = check_schema(df, expected)
        assert result.passed is False
        assert any("year" in e for e in result.errors)


class TestCheckNotEmpty:
    def test_non_empty_dataframe(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = check_not_empty(df)
        assert result.passed is True

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        result = check_not_empty(df)
        assert result.passed is False
        assert any("empty" in e.lower() for e in result.errors)


class TestCheckNoDuplicateKeys:
    def test_no_duplicates(self):
        df = pd.DataFrame({
            "year": [2020, 2021, 2020],
            "donor_code": [1, 1, 2],
        })
        result = check_no_duplicate_keys(df, ["year", "donor_code"])
        assert result.passed is True

    def test_has_duplicates(self):
        df = pd.DataFrame({
            "year": [2020, 2020, 2021],
            "donor_code": [1, 1, 1],
        })
        result = check_no_duplicate_keys(df, ["year", "donor_code"])
        assert result.passed is False
        assert any("duplicate" in e.lower() for e in result.errors)


class TestCheckValueColumnsPopulated:
    def test_populated_values(self):
        df = pd.DataFrame({
            "year": [2020, 2021],
            "value_usd": [100, 200],
            "value_eur": [90, 180],
        })
        result = check_value_columns_populated(df)
        assert result.passed is True

    def test_all_null_column(self):
        df = pd.DataFrame({
            "year": [2020, 2021],
            "value_usd": [None, None],
            "value_eur": [90, 180],
        })
        result = check_value_columns_populated(df)
        assert result.passed is False
        assert any("value_usd" in e for e in result.errors)


class TestCheckValueBounds:
    def test_values_within_bounds(self):
        df = pd.DataFrame({
            "value_usd": [1000000, 2000000],  # 1M, 2M in units
        })
        result = check_value_bounds(df)
        assert result.passed is True

    def test_negative_values_allowed(self):
        # Negative values are normal in ODA data (e.g., debt relief, repayments)
        df = pd.DataFrame({
            "value_usd": [-1000, 2000000],
        })
        result = check_value_bounds(df)
        assert result.passed is True

    def test_insanely_large_values(self):
        df = pd.DataFrame({
            "value_usd": [1e20, 2000000],  # Way too large
        })
        result = check_value_bounds(df)
        assert result.passed is False
        assert any("exceeds" in e.lower() or "sanity" in e.lower() for e in result.errors)


class TestCheckNameMappingsComplete:
    def test_complete_mappings(self):
        df = pd.DataFrame({
            "donor_code": [1, 2],
            "donor_name": ["Austria", "Belgium"],
        })
        result = check_name_mappings_complete(df)
        assert result.passed is True

    def test_missing_name_mapping(self):
        df = pd.DataFrame({
            "donor_code": [1, 2, 3],
            "donor_name": ["Austria", "Belgium", None],
        })
        result = check_name_mappings_complete(df)
        assert result.passed is False
        assert any("unmapped" in e.lower() or "3" in e for e in result.errors)


class TestCheckCriticalDimensions:
    def test_all_critical_present(self):
        df = pd.DataFrame({
            "year": [2023, 2024, 2023, 2024],
            "donor_code": [4, 4, 5, 5],  # France and Germany
        })
        result = check_critical_dimensions(
            df,
            expected_latest_year=2024,
            critical_donors=[4, 5],
        )
        assert result.passed is True

    def test_missing_latest_year(self):
        df = pd.DataFrame({
            "year": [2022, 2023],
            "donor_code": [4, 5],
        })
        result = check_critical_dimensions(
            df,
            expected_latest_year=2024,
            critical_donors=[4, 5],
        )
        assert result.passed is False
        assert any("2024" in e for e in result.errors)

    def test_missing_critical_donor(self):
        df = pd.DataFrame({
            "year": [2024, 2024],
            "donor_code": [4, 6],  # France and Italy, missing Germany (5)
        })
        result = check_critical_dimensions(
            df,
            expected_latest_year=2024,
            critical_donors=[4, 5],
        )
        assert result.passed is False
        assert any("5" in str(e) for e in result.errors)
