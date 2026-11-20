"""Tests for the view contracts."""

import numpy as np
import pandas as pd
import pytest

from src.data.validation.contracts import (
    MAX_SANE_VALUE,
    check_columns,
    check_critical_donors,
    check_keys,
    check_non_empty,
    check_options,
    check_values,
    check_years,
    run_contracts,
)
from src.data.validation.io import LoadedView
from src.data.validation.models import CheckResult, Severity
from src.data.validation.views import CRITICAL_DONORS, get_spec
from tests.data.validation.conftest import MakeView

FINANCING_END = get_spec("financing_view").time["end"]
SECTORS_END = get_spec("sectors_view").time["end"]


def _by_check(results: list[CheckResult]) -> dict[str, CheckResult]:
    """Index results by check name."""
    return {r.check: r for r in results}


def _financing_rows(
    years: tuple[int, ...] = (FINANCING_END,), donors: tuple[str, ...] = CRITICAL_DONORS
) -> list[dict]:
    """One Total ODA row per donor and year."""
    return [
        {
            "year": year,
            "donor_name": donor,
            "indicator_name": "Total ODA",
            "type": "Flows",
            "value_usd_current": 1_000_000.0,
        }
        for year in years
        for donor in donors
    ]


@pytest.fixture
def financing(make_view: MakeView) -> LoadedView:
    """A financing view that satisfies every contract."""
    spec = get_spec("financing_view")
    view = make_view(
        "financing_view", _financing_rows(years=(spec.time["start"], spec.time["end"]))
    )
    return view


def test_clean_view_passes_every_contract(financing: LoadedView) -> None:
    """A well-formed view passes every contract."""
    results = run_contracts(financing)
    failed = [r for r in results if not r.passed]
    assert failed == []
    assert len(results) > 5


def test_empty_view_stops_early(make_view: MakeView) -> None:
    """An empty view fails non_empty and runs nothing that needs rows."""
    view = make_view(
        "financing_view",
        pd.DataFrame(
            columns=[
                "year",
                "donor_name",
                "indicator_name",
                "type",
                "value_usd_current",
            ]
        ),
    )
    results = _by_check(run_contracts(view))
    assert not results["contracts.non_empty"].passed
    assert set(results) == {"contracts.non_empty", "contracts.columns"}


def test_missing_and_wrong_dtype_columns(financing: LoadedView) -> None:
    """A dropped column and a column of the wrong dtype both fail, ints of any width pass."""
    data = financing.data.drop(columns=["pct_of_gni"])
    data["year"] = data["year"].astype("int64")
    data["value_eur_current"] = data["value_eur_current"].astype("string")
    financing.data = data
    [result] = check_columns(financing)
    assert not result.passed
    assert result.severity is Severity.ERROR and result.blocking
    assert set(result.details["column"]) == {"pct_of_gni", "value_eur_current"}
    assert {r.check for r in run_contracts(financing)} == {
        "contracts.non_empty",
        "contracts.columns",
    }


def test_duplicate_and_blank_keys(financing: LoadedView) -> None:
    """Duplicated keys and blank labels fail separately."""
    data = pd.concat([financing.data, financing.data.iloc[[0]]], ignore_index=True)
    data.loc[1, "indicator_name"] = "  "
    financing.data = data
    results = _by_check(check_keys(financing))
    assert results["contracts.unique_keys"].message.startswith("2 rows")
    assert len(results["contracts.keys_populated"].details) == 1


def test_years_outside_window_and_missing_end(make_view: MakeView) -> None:
    """A year outside the window fails, and so does a missing end year."""
    view = make_view("financing_view", _financing_rows(years=(1980, 2000)))
    [result] = check_years(view)
    assert not result.passed
    assert "outside" in result.message and f"end year {FINANCING_END}" in result.message
    assert result.details.to_dict("records") == [
        {"year": 1980, "rows": len(CRITICAL_DONORS)}
    ]


def test_value_nulls_and_magnitude(financing: LoadedView) -> None:
    """Primary nulls are ERROR, other nulls a WARNING with counts, huge values ERROR."""
    data = financing.data
    data.loc[0, "value_usd_current"] = np.nan
    data.loc[1, "value_eur_constant"] = np.nan
    data.loc[2, "value_gbp_current"] = MAX_SANE_VALUE * 10
    data.loc[3, "value_cad_current"] = np.inf
    results = _by_check(check_values(financing))

    primary = results["contracts.primary_value_populated"]
    assert not primary.passed and primary.severity is Severity.ERROR

    others = results["contracts.values_populated"]
    assert not others.passed
    assert others.severity is Severity.WARNING and not others.blocking
    assert "value_eur_constant: 1" in others.message
    assert len(others.details) == 1

    magnitude = results["contracts.value_magnitude"]
    assert not magnitude.passed and magnitude.message.startswith("2 values")


def test_missing_critical_donor(make_view: MakeView) -> None:
    """A critical donor without rows fails."""
    view = make_view("financing_view", _financing_rows(donors=CRITICAL_DONORS[1:]))
    [result] = check_critical_donors(view)
    assert not result.passed
    assert result.details["donor_name"].tolist() == [CRITICAL_DONORS[0]]


def test_options_mismatches(financing: LoadedView) -> None:
    """Listed values without rows, unlisted row values, bad defaults and years all fail."""
    options = financing.options
    options["donor_name"] = [*options["donor_name"][1:], "Atlantis"]
    options["defaults"] = {
        "donor_name": "Atlantis",
        "indicator_name": ["Total ODA", "Nope"],
    }
    options["year"] = {**options["year"], "end": FINANCING_END - 1}
    results = _by_check(check_options(financing))

    assert results["contracts.options_listed_have_rows"].details.to_dict("records") == [
        {"column": "donor_name", "value": "Atlantis"}
    ]
    assert results["contracts.options_rows_listed"].details["value"].tolist() == [
        sorted(CRITICAL_DONORS)[0]
    ]
    assert results["contracts.options_defaults"].details["value"].tolist() == ["Nope"]
    years = results["contracts.options_years"].details
    assert set(years["against"]) == {"spec", "data"}


def _sector_view(
    make_view: MakeView, sector_rows: list[dict], sub_sectors: dict
) -> LoadedView:
    """A sectors view of sector_rows, with sub-sector options as given."""
    view = make_view("sectors_view", sector_rows)
    view.options["sub_sectors_by_sector"] = sub_sectors
    view.options["year"] = {
        "start": SECTORS_END,
        "end": SECTORS_END,
        "base": SECTORS_END,
    }
    return view


def test_sub_sectors_checked_as_pairs(
    make_view: MakeView, sector_rows: list[dict]
) -> None:
    """Sub-sectors are listed per sector; a pair missing from options fails."""
    view = _sector_view(make_view, sector_rows, {"Health": ["Basic Health"]})
    results = _by_check(check_options(view))
    assert results["contracts.options_rows_listed"].passed

    view.options["sub_sectors_by_sector"] = {"Health": ["Health, General"]}
    results = _by_check(check_options(view))
    assert not results["contracts.options_rows_listed"].passed
    assert not results["contracts.options_listed_have_rows"].passed


def test_sub_sectors_without_options_list(
    make_view: MakeView, sector_rows: list[dict]
) -> None:
    """A sectors view whose options lack sub_sectors_by_sector fails."""
    view = make_view("sectors_view", sector_rows)
    results = _by_check(check_options(view))
    unlisted = results["contracts.options_rows_listed"]
    assert "sub_sector_name" in unlisted.details["column"].tolist()


def test_non_empty_passes(financing: LoadedView) -> None:
    """A view with rows passes non_empty and reports its row count."""
    [result] = check_non_empty(financing)
    assert result.passed and result.details is None
