"""Tests for the view options JSON: defaults and names must be among the options."""

import json

import pandas as pd
import pytest

from src.data.analysis_tools import outputs
from src.data.analysis_tools.outputs import generate_view_options

ROWS = pd.DataFrame(
    {
        "year": [2023, 2024],
        "donor_name": ["DAC countries", "France"],
        "indicator_name": ["Bilateral", "Imputed multilateral"],
    }
)
COLUMNS = {"donor_name": [], "indicator_name": [], "year": []}


@pytest.fixture
def tools_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(outputs.PATHS, "TOOLS", tmp_path)
    return tmp_path


def test_defaults_and_names_are_written(tools_dir):
    defaults = {
        "donor_name": "DAC countries",
        "indicator_name": ["Bilateral", "Imputed multilateral"],
    }
    generate_view_options(
        ROWS,
        COLUMNS,
        file_name="v.json",
        defaults=defaults,
        names={"donor_name": {"france": "France"}},
    )
    written = json.loads((tools_dir / "v.json").read_text())
    assert written["defaults"] == defaults
    assert written["names"] == {"france": "France"}


def test_a_renamed_default_fails_the_build(tools_dir):
    with pytest.raises(ValueError, match="default donor_name"):
        generate_view_options(
            ROWS, COLUMNS, file_name="v.json", defaults={"donor_name": "DAC members"}
        )


def test_a_renamed_name_fails_the_build(tools_dir):
    with pytest.raises(ValueError, match="indicator_name not among the options"):
        generate_view_options(
            ROWS,
            COLUMNS,
            file_name="v.json",
            names={"indicator_name": {"total_oda": "Total ODA"}},
        )


def test_a_names_key_reused_across_columns_fails_the_build(tools_dir):
    with pytest.raises(ValueError, match="more than one column"):
        generate_view_options(
            ROWS,
            COLUMNS,
            file_name="v.json",
            names={
                "donor_name": {"main": "France"},
                "indicator_name": {"main": "Bilateral"},
            },
        )
