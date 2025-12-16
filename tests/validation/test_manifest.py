"""Tests for manifest operations."""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from validation.manifest import (
    compute_aggregates,
    compute_distribution,
    load_manifest,
    save_manifest,
    update_manifest,
    compute_historical_variation,
)


class TestComputeAggregates:
    def test_by_donor(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 1, 2, 2],
                "year": [2023, 2024, 2023, 2024],
                "value_usd_constant": [100, 110, 200, 220],
            }
        )
        aggs = compute_aggregates(df, value_column="value_usd_constant")
        assert aggs["by_donor"]["1"] == 210  # 100 + 110
        assert aggs["by_donor"]["2"] == 420  # 200 + 220

    def test_by_year(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 1, 2, 2],
                "year": [2023, 2024, 2023, 2024],
                "value_usd_constant": [100, 110, 200, 220],
            }
        )
        aggs = compute_aggregates(df, value_column="value_usd_constant")
        assert aggs["by_year"]["2023"] == 300  # 100 + 200
        assert aggs["by_year"]["2024"] == 330  # 110 + 220


class TestComputeDistribution:
    def test_basic_stats(self):
        df = pd.DataFrame(
            {
                "value_usd_constant": [10, 20, 30, 40, 50],
            }
        )
        dist = compute_distribution(df, value_column="value_usd_constant")
        assert dist["min"] == 10
        assert dist["max"] == 50
        assert dist["median"] == 30


class TestComputeHistoricalVariation:
    def test_yoy_variation(self):
        df = pd.DataFrame(
            {
                "donor_code": [1, 1, 1, 1],
                "year": [2020, 2021, 2022, 2023],
                "value_usd_constant": [100, 110, 121, 133],  # ~10% growth each year
            }
        )
        variation = compute_historical_variation(df, value_column="value_usd_constant")
        # Should have mean around 0.10 (10%)
        assert 0.05 < variation["overall"]["mean"] < 0.15
        assert variation["overall"]["std"] > 0  # Some variation


class TestManifestIO:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "test_manifest.json"

            manifest = {
                "dataset": "test",
                "schema": {"columns": ["a", "b"]},
                "releases": {},
            }

            save_manifest(manifest, manifest_path)
            loaded = load_manifest(manifest_path)

            assert loaded["dataset"] == "test"
            assert loaded["schema"]["columns"] == ["a", "b"]

    def test_load_nonexistent_returns_empty(self):
        result = load_manifest(Path("/nonexistent/path.json"))
        assert result == {}


class TestUpdateManifest:
    def test_adds_new_release(self):
        manifest = {
            "dataset": "test",
            "schema": {"columns": ["year", "value"]},
            "releases": {},
        }

        df = pd.DataFrame(
            {
                "year": [2023, 2024],
                "donor_code": [1, 1],
                "value_usd_constant": [100, 200],
            }
        )

        updated = update_manifest(
            manifest=manifest,
            release="dec_2024",
            df=df,
            value_column="value_usd_constant",
            key_columns=["year", "donor_code"],
        )

        assert "dec_2024" in updated["releases"]
        assert updated["releases"]["dec_2024"]["row_count"] == 2
