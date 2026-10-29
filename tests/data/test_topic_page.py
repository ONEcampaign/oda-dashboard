"""Tests for the topic page's shared reads: DAC totals and ODA/GNI as the financing view has them."""

import pandas as pd
import pytest

from src.data.config import DAC_COUNTRIES_NAME
from src.data.topic_page import common
from src.data.topic_page.common import oda_gni_table, with_dac_total

AUSTRIA, BELGIUM, EU_INSTITUTIONS, MEXICO = 1, 2, 918, 358
NAMES = {
    AUSTRIA: "Austria",
    BELGIUM: "Belgium",
    EU_INSTITUTIONS: "EU Institutions",
    MEXICO: "Mexico",
}


def _rows(values: dict[int, float], year: int = 2024) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "donor_code": pd.array(list(values), dtype="Int64"),
            "donor_name": [NAMES[code] for code in values],
            "year": year,
            "value": list(values.values()),
        }
    )


def test_dac_total_sums_only_dac_members():
    df = _rows({AUSTRIA: 1.0, BELGIUM: 2.0, EU_INSTITUTIONS: 10.0, MEXICO: 100.0})
    total = with_dac_total(df, ["year"])
    dac = total.loc[total["donor_name"] == DAC_COUNTRIES_NAME, "value"]
    assert dac.tolist() == [3.0]
    assert len(total) == len(df) + 1


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame:
    """oda_gni_table over stubbed reads: Belgium reports no GNI, so the DAC ratio leaves its
    ODA out; constant prices are twice current for everyone."""
    oda = _rows({AUSTRIA: 10.0, BELGIUM: 20.0, EU_INSTITUTIONS: 30.0})
    gni = _rows({AUSTRIA: 1_000.0})
    monkeypatch.setattr(common, "read_total_oda", lambda ctx, **_: oda)
    monkeypatch.setattr(
        common,
        "to_usd_constant",
        lambda df, **_: df.assign(value=df["value"] * 2),
    )
    monkeypatch.setattr(common, "get_member_gni", lambda ctx, *_, **__: gni)
    return oda_gni_table(
        None,
        years=range(2024, 2025),
        providers=NAMES,
        base_year=2024,
        provenance=None,
    ).set_index("donor_name")


def test_members_divide_their_own_oda_by_their_gni(table):
    assert table.loc["Austria", "oda_gni"] == pytest.approx(0.01)
    assert table.loc["Austria", "gap_current"] == pytest.approx(7.0 - 10.0)
    assert pd.isna(table.loc["Belgium", "oda_gni"])
    assert pd.isna(table.loc["EU Institutions", "oda_gni"])


def test_dac_ratio_counts_only_members_reporting_gni(table):
    dac = table.loc[DAC_COUNTRIES_NAME]
    assert dac["oda_current"] == pytest.approx(30.0)
    assert dac["oda_constant"] == pytest.approx(60.0)
    assert dac["oda_gni"] == pytest.approx(10.0 / 1_000.0)
