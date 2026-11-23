"""Tests for a view's options and the archive that ships them with its data."""

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from src.data.analysis_tools.outputs import (
    VIEW_DATA_MEMBER,
    VIEW_OPTIONS_MEMBER,
    build_view_options,
    view_archive_to_stdout,
    write_partitioned_dataset,
    write_view_options,
)

ROWS = pd.DataFrame(
    {
        "year": [2023, 2024],
        "donor_name": ["DAC countries", "France"],
        "indicator_name": ["Bilateral", "Imputed multilateral"],
    }
)
COLUMNS = {"donor_name": [], "indicator_name": [], "year": []}


def test_defaults_and_names_are_included():
    defaults = {
        "donor_name": "DAC countries",
        "indicator_name": ["Bilateral", "Imputed multilateral"],
    }
    options = build_view_options(
        ROWS,
        COLUMNS,
        defaults=defaults,
        names={"donor_name": {"france": "France"}},
    )
    assert options["defaults"] == defaults
    assert options["names"] == {"france": "France"}


def test_a_renamed_default_fails_the_build():
    with pytest.raises(ValueError, match="default donor_name"):
        build_view_options(ROWS, COLUMNS, defaults={"donor_name": "DAC members"})


def test_a_renamed_name_fails_the_build():
    with pytest.raises(ValueError, match="indicator_name not among the options"):
        build_view_options(
            ROWS, COLUMNS, names={"indicator_name": {"total_oda": "Total ODA"}}
        )


def test_a_names_key_reused_across_columns_fails_the_build():
    with pytest.raises(ValueError, match="more than one column"):
        build_view_options(
            ROWS,
            COLUMNS,
            names={
                "donor_name": {"main": "France"},
                "indicator_name": {"main": "Bilateral"},
            },
        )


def test_the_archive_carries_the_data_and_its_options(capsysbinary):
    options = build_view_options(ROWS, COLUMNS)
    view_archive_to_stdout(ROWS, options)
    archive = zipfile.ZipFile(io.BytesIO(capsysbinary.readouterr().out))
    assert sorted(archive.namelist()) == sorted([VIEW_DATA_MEMBER, VIEW_OPTIONS_MEMBER])
    assert json.loads(archive.read(VIEW_OPTIONS_MEMBER)) == options
    data = pd.read_parquet(io.BytesIO(archive.read(VIEW_DATA_MEMBER)))
    assert data["donor_name"].astype(str).tolist() == ROWS["donor_name"].tolist()
    assert len(data) == len(ROWS)


def test_view_options_are_written_under_root(tmp_path: Path) -> None:
    options = build_view_options(ROWS, COLUMNS)
    write_view_options(options, "view_options.json", root=tmp_path)
    assert json.loads((tmp_path / "view_options.json").read_text()) == options


def test_partitioned_dataset_is_written_under_root(tmp_path: Path) -> None:
    rows = ROWS.assign(donor_slug=["dac-countries", "france"])
    write_partitioned_dataset(rows, "view", ["donor_slug"], root=tmp_path)
    partitions = sorted(p.name for p in (tmp_path / "view").iterdir())
    assert partitions == ["donor_slug=dac-countries", "donor_slug=france"]
    data = pd.read_parquet(tmp_path / "view")
    assert sorted(data["year"].tolist()) == ROWS["year"].tolist()


def test_each_partition_is_one_file_holding_all_its_rows(tmp_path: Path) -> None:
    # The frontend fetches only part-0.parquet, so a second file would drop rows from charts.
    n_partitions, rows_per_partition = 1_500, 3
    rows = pd.DataFrame(
        {
            # Interleaved, so each partition's rows are spread across the frame.
            "donor_slug": [f"d{i}" for i in range(n_partitions)] * rows_per_partition,
            "year": [y for y in range(rows_per_partition) for _ in range(n_partitions)],
            "value_usd_current": 1,
        }
    )
    write_partitioned_dataset(rows, "view", ["donor_slug"], root=tmp_path)
    part_dirs = list((tmp_path / "view").iterdir())
    assert len(part_dirs) == n_partitions
    for part_dir in part_dirs:
        assert [f.name for f in part_dir.iterdir()] == ["part-0.parquet"]
        assert len(pd.read_parquet(part_dir / "part-0.parquet")) == rows_per_partition


def test_partition_column_with_missing_values_raises(tmp_path: Path) -> None:
    rows = ROWS.assign(donor_slug=["dac-countries", None])
    with pytest.raises(ValueError, match="missing values"):
        write_partitioned_dataset(rows, "view", ["donor_slug"], root=tmp_path)
