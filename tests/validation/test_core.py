"""Tests for core validation orchestration."""

import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from validation.core import validate_dataset, validate_all
from validation.models import ValidationReport


@pytest.fixture
def sample_parquet(tmp_path):
    """Create a sample parquet file for testing."""
    df = pd.DataFrame({
        "year": [2022, 2023, 2024] * 4,
        "donor_code": [4, 4, 4, 5, 5, 5, 6, 6, 6, 7, 7, 7],
        "donor_name": ["France"] * 3 + ["Germany"] * 3 + ["Italy"] * 3 + ["Japan"] * 3,
        "indicator": ["total_oda"] * 12,
        "indicator_name": ["Total ODA"] * 12,
        "type": ["Grant equivalents"] * 12,
        "value_usd_current": [1000, 1100, 1150] * 4,
        "value_usd_constant": [1000, 1050, 1100] * 4,
        "value_eur_current": [900, 990, 1035] * 4,
        "value_eur_constant": [900, 945, 990] * 4,
        "value_gbp_current": [800, 880, 920] * 4,
        "value_gbp_constant": [800, 840, 880] * 4,
        "value_cad_current": [1300, 1430, 1495] * 4,
        "value_cad_constant": [1300, 1365, 1430] * 4,
    })

    path = tmp_path / "test_view.parquet"
    table = pa.Table.from_pandas(df)
    pq.write_table(table, path)

    return path, df


class TestValidateDataset:
    def test_valid_dataset_passes(self, sample_parquet, tmp_path):
        path, df = sample_parquet

        # Create a minimal config override for testing
        dataset_config = {
            "file": path.name,
            "key_columns": ["year", "donor_code", "indicator"],
            "value_column": "value_usd_constant",
            "required_columns": list(df.columns),
            "critical_donors": [4, 5],  # France, Germany
        }

        result = validate_dataset(
            dataset_name="test_view",
            release="dec_2024",
            cache_dir=tmp_path,
            dataset_config=dataset_config,
            manifests_dir=tmp_path / "manifests",
            update_manifest=False,
        )

        assert isinstance(result, ValidationReport)
        assert result.has_blocking_errors is False

    def test_missing_file_fails(self, tmp_path):
        dataset_config = {
            "file": "nonexistent.parquet",
            "key_columns": ["year"],
            "value_column": "value",
            "required_columns": ["year", "value"],
            "critical_donors": [],
        }

        result = validate_dataset(
            dataset_name="test",
            release="dec_2024",
            cache_dir=tmp_path,
            dataset_config=dataset_config,
            manifests_dir=tmp_path / "manifests",
            update_manifest=False,
        )

        assert result.has_blocking_errors is True
