"""Tests for the recipients and gender views' data handling."""

import pandas as pd
import pytest

from src.data.analysis_tools.gender import derive_not_screened
from src.data.analysis_tools.recipients import (
    aggregate_recipient_names,
    canonical_recipients,
)


def dac2a(rows: list[tuple[float | None, str]]) -> pd.DataFrame:
    """Build DAC2A rows from (recipient_code, recipient_name)."""
    return pd.DataFrame(rows, columns=["recipient_code", "recipient_name"])


def test_canonical_recipients_fills_codes_and_drops_excluded_groups():
    df = dac2a(
        [
            (248.0, "Kenya"),
            (None, "Indus Basin"),  # filled from DAC2A_MISSING_RECIPIENT_CODES
            (10_200.0, "All recipients"),  # excluded
            (10_100.0, "Developing countries, Total"),  # renamed
        ]
    )
    out = canonical_recipients(df)
    assert out["recipient_name"].tolist() == [
        "Kenya",
        "Indus Basin",
        "ODA eligible countries",
    ]
    assert (
        out.loc[out["recipient_name"] == "Indus Basin", "recipient_code"].item() == 650
    )


def test_canonical_recipients_raises_when_two_codes_share_a_name():
    with pytest.raises(ValueError, match="shared by more than one code"):
        canonical_recipients(dac2a([(248.0, "Kenya"), (249.0, "Kenya")]))


def test_aggregate_recipient_names_leaves_out_unspecified_codes():
    df = dac2a(
        [(10_001.0, "Africa"), (10_280.0, "Africa, unspecified"), (248.0, "Kenya")]
    )
    assert aggregate_recipient_names(df) == ["Africa"]


def test_not_screened_is_allocable_minus_screened():
    index = pd.MultiIndex.from_tuples(
        [(2023, 302), (2023, 4)], names=["year", "donor_code"]
    )
    scores = {
        "principal": pd.Series([1.0, 2.0], index=index),
        "significant": pd.Series([3.0, 0.0], index=index),
        "not_targeted": pd.Series([6.0, 1.0], index=index),
    }
    allocable = pd.Series([10.0, 8.0], index=index)
    out = derive_not_screened(scores, allocable).set_index(
        ["donor_code", "indicator_name"]
    )
    assert out.loc[(302, "Not screened"), "value"] == 0.0
    assert out.loc[(4, "Not screened"), "value"] == 5.0
    assert out.groupby(level="donor_code")["value"].sum().to_dict() == {
        4: 8.0,
        302: 10.0,
    }


def test_not_screened_rejects_screened_rows_outside_the_allocable_total():
    index = pd.MultiIndex.from_tuples([(2023, 302)], names=["year", "donor_code"])
    other = pd.MultiIndex.from_tuples([(2023, 4)], names=["year", "donor_code"])
    scores = {"principal": pd.Series([1.0], index=other)}
    with pytest.raises(ValueError, match="outside the allocable total"):
        derive_not_screened(scores, pd.Series([1.0], index=index))
