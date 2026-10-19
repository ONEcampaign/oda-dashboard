"""Tests for a view's options and the archive that ships them with its data."""

import io
import json
import zipfile

import pandas as pd
import pytest

from src.data.analysis_tools.outputs import (
    VIEW_DATA_MEMBER,
    VIEW_OPTIONS_MEMBER,
    build_view_options,
    view_archive_to_stdout,
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
