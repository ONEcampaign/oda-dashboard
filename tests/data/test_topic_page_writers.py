"""Tests for the topic page writers: key numbers, the ODA/GNI gap and the COVID-19 column."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.data.config import DAC_COUNTRIES_NAME
from src.data.topic_page import common, overview, total_oda_gni
from src.data.topic_page.total_excl_donor import (
    COVID_ODA,
    IDRC,
    PRE_COVID_YEAR,
    TOTAL_ODA,
    add_covid_oda,
    check_total_oda_present,
)
from src.data.topic_page.ukraine import PRE_INVASION_YEAR


@pytest.fixture
def topic_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the overview and ODA/GNI writers at an empty folder."""
    paths = SimpleNamespace(TOPIC_PAGE=tmp_path)
    monkeypatch.setattr(overview, "PATHS", paths)
    monkeypatch.setattr(total_oda_gni, "PATHS", paths)
    return tmp_path


def _dac(year: int) -> pd.DataFrame:
    """oda_gni_table rows for DAC countries in year - 1 and year."""
    return pd.DataFrame(
        {
            "donor_name": DAC_COUNTRIES_NAME,
            "year": [year - 1, year],
            "oda_current": [200.0, 160.0],
            "oda_constant": [220.0, 170.0],
            "oda_gni": [0.0035, 0.0028],
            "gap_current": [100.0, 150.0],
        }
    )


def test_constant_year_is_the_latest_aggregate_year() -> None:
    assert common.CONSTANT_YEAR == common.LATEST_YEAR_AGG


def test_short_window_holds_the_comparison_years() -> None:
    """oda_covid.csv's key numbers compare with years the short read includes."""
    assert common.SHORT_START_YEAR <= min(PRE_COVID_YEAR, PRE_INVASION_YEAR)


def test_update_key_number_drops_retired_keys(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    path.write_text(json.dumps({"latest_year": "2024", "retired_key": "x"}))
    common.update_key_number(path, {"latest_year": "2025"})
    assert json.loads(path.read_text()) == {"latest_year": "2025"}


def test_update_key_number_rejects_undeclared_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="new_key"):
        common.update_key_number(tmp_path / "keys.json", {"new_key": "1"})


def test_total_oda_change_has_no_space_before_percent(topic_page: Path) -> None:
    overview.total_aid_key_number(_dac(2031))
    numbers = json.loads((topic_page / common.KEY_NUMBERS_FILE).read_text())
    change = 170.0 / 220.0 - 1
    assert numbers["total_oda_change"] == f"{change:.1%}"
    assert numbers["latest_year"] == "2031"


def test_aid_gni_first_line_names_the_data_year(topic_page: Path) -> None:
    overview.aid_gni_key_number(_dac(2031))
    published = pd.read_csv(topic_page / "oda_gni_sm.csv")
    assert published["first_line"].tolist() == ["As of 2031"]


def test_gap_without_gni_publishes_empty(topic_page: Path) -> None:
    table = pd.DataFrame(
        {
            "donor_name": ["Austria", "Estonia"],
            "year": [2001, 2001],
            "oda_current": [500.0, 2.0],
            "oda_constant": [1_000.0, 4.0],
            "oda_gni": [0.002, np.nan],
            "gap_current": [1_500.0, np.nan],
        }
    )
    total_oda_gni.oda_gni_year_columns(table)
    published = pd.read_csv(
        topic_page / "oda_gni_single_year_ts.csv", keep_default_na=False
    ).set_index("Donor")
    assert published.at["Austria", "ODA short of 0.7% commitment"] == "3.00 billion"
    assert published.at["Estonia", "ODA short of 0.7% commitment"] == ""
    assert published.at["Estonia", "ODA/GNI"] == ""


def test_covid_oda_is_missing_only_where_the_series_has_no_figure() -> None:
    covid = pd.DataFrame(
        {"donor_name": "Austria", "year": [2020, 2021], "value": [1.0, 2.0]}
    )
    df = pd.DataFrame(
        {
            "donor_name": ["Austria"] * 4 + ["Latvia"],
            "year": [2019, 2020, 2021, 2022, 2021],
        }
    )
    result = add_covid_oda(df, covid).set_index(["donor_name", "year"])[COVID_ODA]
    assert result[("Austria", 2019)] == 0
    assert result[("Austria", 2021)] == 2.0
    assert pd.isna(result[("Austria", 2022)])
    assert pd.isna(result[("Latvia", 2021)])
    assert len(result) == len(df)


def test_missing_total_oda_raises() -> None:
    wide = pd.DataFrame(
        {
            "donor_name": ["Austria", "Belgium"],
            "year": [2024, 2024],
            TOTAL_ODA: [1.0, np.nan],
            IDRC: [0.1, 0.2],
        }
    )
    with pytest.raises(ValueError, match="Belgium"):
        check_total_oda_present(wide)
