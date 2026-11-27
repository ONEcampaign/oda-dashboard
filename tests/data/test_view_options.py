"""Tests for a view's options and the archive that ships them with its data."""

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from src.data.analysis_tools.outputs import (
    VERSION_HEX_LENGTH,
    VIEW_DATA_MEMBER,
    VIEW_OPTIONS_MEMBER,
    build_view_options,
    partition_pairs,
    view_archive_to_stdout,
    write_partitioned_dataset,
    write_versioned_dataset,
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


PAIR_ROWS = pd.DataFrame(
    {
        "donor_slug": ["france", "france", "germany"],
        "recipient_slug": ["kenya", "mali", "kenya"],
        "year": [2023, 2024, 2024],
        "value_usd_current": [1, 2, 3],
    }
)
PAIR_COLS = ["donor_slug", "recipient_slug"]


def test_dataset_version_is_deterministic_and_content_addressed(tmp_path: Path) -> None:
    first = write_versioned_dataset(PAIR_ROWS, "view", PAIR_COLS, root=tmp_path / "a")
    second = write_versioned_dataset(PAIR_ROWS, "view", PAIR_COLS, root=tmp_path / "b")
    changed = write_versioned_dataset(
        PAIR_ROWS.assign(value_usd_current=[1, 2, 4]),
        "view",
        PAIR_COLS,
        root=tmp_path / "c",
    )

    assert first == second
    assert changed != first
    assert len(first) == VERSION_HEX_LENGTH
    assert set(first) <= set("0123456789abcdef")  # deploy.yml prunes only hex names


def test_a_rewrite_leaves_only_the_new_version(tmp_path: Path) -> None:
    old = write_versioned_dataset(PAIR_ROWS, "view", PAIR_COLS, root=tmp_path)
    new = write_versioned_dataset(PAIR_ROWS.head(2), "view", PAIR_COLS, root=tmp_path)

    assert old != new
    assert [p.name for p in (tmp_path / "view").iterdir()] == [new]
    data = pd.read_parquet(tmp_path / "view" / new)
    assert len(data) == 2


def test_partition_pairs_are_the_written_partition_dirs(tmp_path: Path) -> None:
    version = write_versioned_dataset(PAIR_ROWS, "view", PAIR_COLS, root=tmp_path)
    version_dir = tmp_path / "view" / version

    pairs = partition_pairs(version_dir, *PAIR_COLS)

    on_disk = {
        (d.name.removeprefix("donor_slug="), r.name.removeprefix("recipient_slug="))
        for d in version_dir.iterdir()
        for r in d.iterdir()
    }
    assert {(d, r) for d, recipients in pairs.items() for r in recipients} == on_disk
    assert pairs == {"france": ["kenya", "mali"], "germany": ["kenya"]}


def test_partition_pairs_reject_another_layout(tmp_path: Path) -> None:
    write_partitioned_dataset(PAIR_ROWS, "view", ["donor_slug"], root=tmp_path)
    with pytest.raises(ValueError, match="recipient_slug="):
        partition_pairs(tmp_path / "view", *PAIR_COLS)
