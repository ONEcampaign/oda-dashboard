"""Tests for donor groups, the long-to-wide pivot and indicator naming."""

import pandas as pd
import pytest

from src.data.analysis_tools.naming import map_config_values
from src.data.analysis_tools.transformations import (
    build_donor_group_totals,
    drop_empty_values,
    widen_currency_price,
)
from src.data.config import (
    DAC_COUNTRIES,
    DONOR_GROUPS,
    EU_INSTITUTIONS,
    NON_DAC_COUNTRIES,
)

US, SAUDI_ARABIA, EU_INSTITUTIONS_CODE = 302, 566, 918


def test_all_bilateral_donors_is_dac_plus_non_dac_without_eu_institutions():
    assert US in DAC_COUNTRIES and SAUDI_ARABIA in NON_DAC_COUNTRIES
    assert EU_INSTITUTIONS_CODE in EU_INSTITUTIONS
    df = pd.DataFrame(
        {
            "year": [2020] * 3,
            "donor_code": [US, SAUDI_ARABIA, EU_INSTITUTIONS_CODE],
            "value": [10.0, 2.0, 5.0],
        }
    )
    totals = build_donor_group_totals(df, ["year"])
    assert set(totals) == set(DONOR_GROUPS)
    value = {name: frame["value"].sum() for name, frame in totals.items()}
    assert value["All bilateral donors"] == 12.0
    assert (
        value["All bilateral donors"]
        == value["DAC countries"] + value["Non-DAC countries"]
    )


def long_frame() -> pd.DataFrame:
    """Two currency-price rows for one donor-year."""
    return pd.DataFrame(
        {
            "year": [2020, 2020],
            "donor_name": ["US", "US"],
            "currency": ["USD", "EUR"],
            "price": ["current", "current"],
            "value": [1.0, 0.9],
        }
    )


def test_widen_pivots_currency_and_price_into_columns():
    wide = widen_currency_price(long_frame(), index_cols=("year", "donor_name"))
    assert list(wide.columns) == [
        "year",
        "donor_name",
        "value_eur_current",
        "value_usd_current",
    ]


def test_widen_raises_on_a_duplicate_key():
    df = pd.concat([long_frame(), long_frame().head(1)], ignore_index=True)
    with pytest.raises(ValueError, match="share a key"):
        widen_currency_price(df, index_cols=("year", "donor_name"))


def test_drop_empty_values_drops_missing_and_zero_only():
    df = pd.DataFrame({"value": [1.0, 0.0, None, -2.0]})
    assert drop_empty_values(df, "test")["value"].tolist() == [1.0, -2.0]


def test_map_config_values_raises_on_an_unknown_code():
    codes = pd.Series(["A", "B"])
    with pytest.raises(
        ValueError, match=r"Indicator codes with no entry in config: \['B'\]"
    ):
        map_config_values(codes, {"A": "Alpha"}, what="Indicator codes")
