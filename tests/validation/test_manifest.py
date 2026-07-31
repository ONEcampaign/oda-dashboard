"""Tests for manifest operations.

Manifests are keyed by name, matching what the four views publish. Several tests below assert
that a dimension is present and non-empty: the failure this guards against is a manifest that
writes an empty list for a dimension, which then makes every later release compare against
nothing and pass.
"""

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
                "donor_name": ["Austria", "Austria", "Belgium", "Belgium"],
                "year": [2023, 2024, 2023, 2024],
                "value_usd_constant": [100, 110, 200, 220],
            }
        )
        aggs = compute_aggregates(df, value_column="value_usd_constant")
        assert aggs["by_donor"]["Austria"] == 210  # 100 + 110
        assert aggs["by_donor"]["Belgium"] == 420  # 200 + 220

    def test_by_year(self):
        df = pd.DataFrame(
            {
                "donor_name": ["Austria", "Austria", "Belgium", "Belgium"],
                "year": [2023, 2024, 2023, 2024],
                "value_usd_constant": [100, 110, 200, 220],
            }
        )
        aggs = compute_aggregates(df, value_column="value_usd_constant")
        assert aggs["by_year"]["2023"] == 300  # 100 + 200
        assert aggs["by_year"]["2024"] == 330  # 110 + 220

    def test_by_donor_sector_is_keyed_by_both(self):
        df = pd.DataFrame(
            {
                "donor_name": ["France", "France", "Germany"],
                "sector_name": ["Health", "Education", "Health"],
                "value_usd_constant": [100, 50, 200],
            }
        )
        aggs = compute_aggregates(df, value_column="value_usd_constant")
        assert aggs["by_donor_sector"]["France|Health"] == 100
        assert aggs["by_donor_sector"]["Germany|Health"] == 200

    def test_absent_dimensions_are_omitted_not_emptied(self):
        # financing_view has no recipient; the key should be missing rather than {}, so an
        # empty aggregate can never be mistaken for "nothing changed".
        df = pd.DataFrame(
            {"donor_name": ["Austria"], "year": [2024], "value_usd_constant": [100]}
        )
        aggs = compute_aggregates(df, value_column="value_usd_constant")
        assert "by_recipient" not in aggs
        assert "by_sub_sector" not in aggs
        assert aggs["by_donor"]


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
                "donor_name": ["Austria"] * 4,
                "year": [2020, 2021, 2022, 2023],
                "value_usd_constant": [100, 110, 121, 133],  # ~10% growth each year
            }
        )
        variation = compute_historical_variation(df, value_column="value_usd_constant")
        # Should have mean around 0.10 (10%)
        assert 0.05 < variation["overall"]["mean"] < 0.15
        assert variation["by_donor"]["Austria"]["mean"] > 0


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
                "donor_name": ["Austria", "Austria"],
                "value_usd_constant": [100, 200],
            }
        )

        updated = update_manifest(
            manifest=manifest,
            release="dec_2024",
            df=df,
            value_column="value_usd_constant",
            key_columns=["year", "donor_name"],
        )

        release = updated["releases"]["dec_2024"]
        assert release["row_count"] == 2
        assert release["donors_present"] == ["Austria"]
        assert release["aggregates"]["by_donor"]["Austria"] == 300

    def test_missing_key_column_raises(self):
        # Writing a manifest from a frame missing a key column would record an empty dimension,
        # and every later release would then compare against nothing and pass.
        df = pd.DataFrame({"year": [2024], "value_usd_constant": [100]})

        with pytest.raises(ValueError, match="key columns absent"):
            update_manifest(
                manifest={},
                release="dec_2024",
                df=df,
                value_column="value_usd_constant",
                key_columns=["year", "donor_name"],
            )
