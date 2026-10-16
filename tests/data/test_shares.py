"""Tests for the share helpers."""

import numpy as np
import pandas as pd

from src.data.analysis_tools.transformations import (
    add_share_of_gni,
    add_share_of_group_total,
    add_share_of_reference_total,
    add_share_of_total_oda,
    safe_share,
)


def test_safe_share_returns_nan_for_a_zero_denominator():
    shares = safe_share(pd.Series([1.0, 1.0]), pd.Series([4.0, 0.0]))
    assert shares.iloc[0] == 0.25
    assert np.isnan(shares.iloc[1])


def test_group_total_shares_sum_to_one_and_handle_zero_totals():
    df = pd.DataFrame(
        {
            "donor_name": ["A", "A", "B", "B"],
            "indicator_name": ["x", "y", "x", "y"],
            "value_usd_current": [3.0, 1.0, 0.0, 0.0],
        }
    )
    out = add_share_of_group_total(df, ["donor_name"], "pct")
    assert out.loc[out["donor_name"] == "A", "pct"].tolist() == [0.75, 0.25]
    assert out.loc[out["donor_name"] == "B", "pct"].isna().all()


def test_reference_total_sums_across_indicators():
    df = pd.DataFrame(
        {
            "year": [2020] * 4,
            "donor_name": ["All", "All", "US", "US"],
            "recipient_name": ["Kenya"] * 4,
            "indicator_name": ["Bilateral", "Imputed", "Bilateral", "Imputed"],
            "value_usd_current": [6.0, 4.0, 3.0, 1.0],
        }
    )
    out = add_share_of_reference_total(
        df, "donor_name", "All", ["year", "recipient_name"], "pct"
    )
    assert out.loc[out["donor_name"] == "US", "pct"].tolist() == [0.3, 0.1]


def test_share_of_total_oda():
    df = pd.DataFrame(
        {
            "year": [2020, 2020],
            "donor_name": ["US", "US"],
            "indicator_name": ["Total ODA", "Grants"],
            "value_usd_current": [200.0, 150.0],
        }
    )
    out = add_share_of_total_oda(df)
    assert out["pct_of_total_oda"].tolist() == [1.0, 0.75]


def test_group_share_of_gni_uses_only_members_with_gni():
    df = pd.DataFrame(
        {
            "year": [2020, 2020],
            "donor_name": ["United States", "Non-DAC countries"],
            "indicator_name": ["Total ODA", "Total ODA"],
            "value_usd_current": [10.0, 6.0],
        }
    )
    # Türkiye reports GNI; Saudi Arabia, the other Non-DAC member here, does not.
    member_gni = pd.DataFrame(
        {
            "donor_code": [302, 55],
            "donor_name": ["United States", "Türkiye"],
            "year": [2020, 2020],
            "value": [1000.0, 100.0],
        }
    )
    members = pd.DataFrame(
        {
            "year": [2020, 2020, 2020],
            "donor_code": [302, 55, 566],
            "indicator_name": ["Total ODA"] * 3,
            "value": [10.0, 2.0, 4.0],
        }
    )
    out = add_share_of_gni(df, member_gni, members).set_index("donor_name")[
        "pct_of_gni"
    ]
    assert out["United States"] == 0.01
    # Only Türkiye's 2 counts against its GNI of 100, not the group's full 6.
    assert out["Non-DAC countries"] == 0.02
