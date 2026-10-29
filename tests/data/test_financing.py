"""Tests for the financing view's data handling."""

import pandas as pd
import pytest

from src.data.analysis_tools.financing import (
    FINANCING_COLUMNS,
    check_one_type_per_series,
    drop_grants_split,
    split_grants,
    sum_by_name,
    to_financing_rows,
    years_missing_grants,
)
from src.data.config import PSI, TOTAL_ODA

US, FRANCE = 302, 4


def query_rows(rows: list[tuple[int, int, str, float]]) -> pd.DataFrame:
    """Build a run_query result from (year, donor_code, basis, value)."""
    return pd.DataFrame(
        {
            "year": [y for y, _, _, _ in rows],
            "donor_code": [d for _, d, _, _ in rows],
            "donor_name": [
                "United States" if d == US else "France" for _, d, _, _ in rows
            ],
            "basis": pd.Categorical([b for _, _, b, _ in rows]),
            "value": [v for _, _, _, v in rows],
        }
    )


def test_type_follows_the_basis_of_each_row():
    raw = query_rows(
        [(2017, US, "net_disbursement", 1.0), (2018, US, "grant_equivalent", 2.0)]
    )
    rows = to_financing_rows(raw, TOTAL_ODA)
    assert list(rows.columns) == FINANCING_COLUMNS
    assert rows["type"].tolist() == ["Flows", "Grant equivalents"]


def test_a_basis_with_no_financing_type_raises():
    raw = query_rows([(2020, US, "gross_disbursement", 1.0)])
    with pytest.raises(ValueError, match="Bases with no entry in config"):
        to_financing_rows(raw, TOTAL_ODA)


def test_psi_transition_parts_are_summed():
    # 2023-24: 11030 holds PSI under the provisional methods, 11040 under the revised ones.
    raw = query_rows(
        [(2023, US, "grant_equivalent", 260.0), (2023, US, "grant_equivalent", 416.0)]
    )
    summed = sum_by_name(to_financing_rows(raw, PSI))
    assert summed["value"].tolist() == [676.0]


def test_a_series_read_twice_raises():
    raw = query_rows(
        [(2020, US, "grant_equivalent", 10.0), (2020, US, "grant_equivalent", 10.0)]
    )
    with pytest.raises(ValueError, match="read more than once"):
        sum_by_name(to_financing_rows(raw, TOTAL_ODA))


def total_oda(rows: list[tuple[int, int, float]]) -> pd.DataFrame:
    """Build Total ODA financing rows from (year, donor_code, value)."""
    return to_financing_rows(
        query_rows([(y, d, "grant_equivalent", v) for y, d, v in rows]), TOTAL_ODA
    )


def grants_rows(rows: list[tuple[int, int, float]]) -> pd.DataFrame:
    """Build a grants-flow read from (year, donor_code, value)."""
    return pd.DataFrame(rows, columns=["year", "donor_code", "value"])


def test_split_grants_derives_non_grants_with_total_odas_type():
    split = split_grants(
        total_oda([(2020, US, 100.0), (2021, US, 90.0)]),
        grants_rows([(2020, US, 80.0)]),
    ).set_index(["year", "indicator_name"])
    assert split.loc[(2020, "Grants"), "value"] == 80.0
    assert split.loc[(2020, "Non-grants"), "value"] == 20.0
    assert set(split["type"]) == {"Grant equivalents"}
    # No grants in 2021: both halves are missing, not zero.
    assert split.loc[[(2021, "Grants"), (2021, "Non-grants")], "value"].isna().all()


def test_grants_without_total_oda_raise():
    with pytest.raises(ValueError, match="no Total ODA"):
        split_grants(total_oda([(2020, US, 100.0)]), grants_rows([(2021, US, 80.0)]))


def test_years_missing_grants_tolerates_small_gaps_only():
    members = {US: "United States", FRANCE: "France"}
    totals = grants_rows(
        [
            (2023, US, 199.0),
            # 2023: France lacks grants but is 0.5% of Total ODA, within the threshold.
            (2023, FRANCE, 1.0),
            # 2025: only France reports grants; the US holds 90% of Total ODA.
            (2025, US, 90.0),
            (2025, FRANCE, 10.0),
        ]
    )
    grants = grants_rows([(2023, US, 190.0), (2025, FRANCE, 9.0)])
    assert years_missing_grants(totals, grants, members) == {2025: pytest.approx(0.9)}


def test_a_zero_grants_value_counts_as_reported():
    totals = grants_rows([(2020, US, 10.0)])
    assert years_missing_grants(totals, grants_rows([(2020, US, 0.0)]), [US]) == {}
    assert years_missing_grants(
        totals, grants_rows([(2020, US, float("nan"))]), [US]
    ) == {2020: pytest.approx(1.0)}


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
    assert sorted(zip(kept["year"], kept["indicator_name"], strict=True)) == [
        (2024, "Grants"),
        (2025, "Total ODA"),
    ]


def test_a_series_with_two_types_in_one_year_raises():
    financing = pd.DataFrame(
        {
            "year": [2020, 2020],
            "donor_name": ["United States"] * 2,
            "indicator_name": [TOTAL_ODA] * 2,
            "type": ["Flows", "Grant equivalents"],
        }
    )
    with pytest.raises(ValueError, match="more than one basis"):
        check_one_type_per_series(financing)
