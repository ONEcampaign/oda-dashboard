"""Tests for the financing view's data handling."""

import pandas as pd
import pytest

from src.data.analysis_tools.financing import (
    drop_grants_split,
    resolve_indicator_duplicates,
    split_grants,
    years_missing_grants,
)

US, FRANCE = 302, 4


def dac1_rows(rows: list[tuple[int, str, float]]) -> pd.DataFrame:
    """Build raw DAC1 rows for one donor from (year, indicator code, value)."""
    return pd.DataFrame(
        [
            {"year": y, "donor_code": US, "one_indicator": code, "value": v}
            for y, code, v in rows
        ]
    )


def test_equal_aliases_keep_one_row():
    raw = dac1_rows([(2020, "DAC1.10.1015", 10.0), (2020, "DAC1.10.11015", 10.0)])
    assert len(resolve_indicator_duplicates(raw)) == 1


def test_a_missing_alias_never_replaces_a_real_value():
    raw = dac1_rows(
        [(2020, "DAC1.10.1015", float("nan")), (2020, "DAC1.10.11015", 5.0)]
    )
    assert resolve_indicator_duplicates(raw)["value"].tolist() == [5.0]


def test_disagreeing_aliases_raise():
    raw = dac1_rows([(2020, "DAC1.10.1015", 10.0), (2020, "DAC1.10.11015", 12.0)])
    with pytest.raises(ValueError, match="Conflicting values"):
        resolve_indicator_duplicates(raw)


def test_psi_transition_parts_are_both_kept():
    # 2023-24: 11030 holds PSI under the provisional methods, 11040 under the revised ones.
    raw = dac1_rows([(2023, "DAC1.60.11030", 260.0), (2023, "DAC1.60.11040", 416.0)])
    kept = resolve_indicator_duplicates(raw)
    assert sorted(kept["one_indicator"]) == ["DAC1.60.11030", "DAC1.60.11040"]


def test_split_grants_derives_non_grants():
    raw = pd.DataFrame(
        {
            "year": [2020, 2020, 2021],
            "donor_code": [US, US, US],
            "fund_flows": [
                "Grant equivalents",
                "Disbursements, grants",
                "Grant equivalents",
            ],
            "value": [100.0, 80.0, 90.0],
        }
    )
    split = split_grants(raw, ["year", "donor_code"]).set_index(
        ["year", "indicator_name"]
    )
    assert split.loc[(2020, "Grants"), "value"] == 80.0
    assert split.loc[(2020, "Non-grants"), "value"] == 20.0
    # No grants measure in 2021: both halves are missing, not zero.
    assert split.loc[[(2021, "Grants"), (2021, "Non-grants")], "value"].isna().all()


def test_split_grants_rejects_an_unknown_fund_flow():
    raw = pd.DataFrame(
        {
            "year": [2020],
            "donor_code": [US],
            "fund_flows": ["Commitments"],
            "value": [1.0],
        }
    )
    with pytest.raises(ValueError, match="Fund flows with no entry in config"):
        split_grants(raw, ["year", "donor_code"])


def usd_current(rows: list[tuple[int, int, str, float]]) -> pd.DataFrame:
    """Build current-USD rows from (year, donor_code, indicator_name, value)."""
    return pd.DataFrame(rows, columns=["year", "donor_code", "indicator_name", "value"])


def test_years_missing_grants_tolerates_small_gaps_only():
    members = {US: "United States", FRANCE: "France"}
    df = usd_current(
        [
            # 2023: France lacks grants but is 0.5% of Total ODA, within the threshold.
            (2023, US, "Total ODA", 199.0),
            (2023, US, "Grants", 190.0),
            (2023, FRANCE, "Total ODA", 1.0),
            # 2025: only France reports grants; the US holds 90% of Total ODA.
            (2025, US, "Total ODA", 90.0),
            (2025, FRANCE, "Total ODA", 10.0),
            (2025, FRANCE, "Grants", 9.0),
        ]
    )
    assert years_missing_grants(df, members) == {2025: pytest.approx(0.9)}


def test_drop_grants_split_only_drops_the_split_in_given_years():
    group = pd.DataFrame(
        {
            "year": [2024, 2025, 2025],
            "donor_name": ["DAC countries"] * 3,
            "indicator_name": ["Grants", "Grants", "Total ODA"],
            "value": [1.0, 1.0, 2.0],
        }
    )
    kept = drop_grants_split(group, {2025: 0.9})
    assert sorted(zip(kept["year"], kept["indicator_name"])) == [
        (2024, "Grants"),
        (2025, "Total ODA"),
    ]
