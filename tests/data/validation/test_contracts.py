"""Tests for the view contracts."""

import numpy as np
import pandas as pd
import pytest

from src.data.config import DAC_COUNTRIES_NAME, ODA_ELIGIBLE
from src.data.validation.contracts import (
    ANCHOR_MAX_UNITS,
    ANCHOR_MIN_UNITS,
    CURRENCY_PER_USD_MAX,
    CURRENCY_PER_USD_MIN,
    MAX_SANE_VALUE,
    PCT_OF_GNI_LIMIT,
    VALUE_NULL_ERROR_FRACTION,
    check_anchor,
    check_anchor_currencies,
    check_columns,
    check_critical_donors,
    check_gni_share,
    check_keys,
    check_non_empty,
    check_options,
    check_types,
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
TYPES: tuple[str, ...] = ("Flows", "Grant equivalents")
# Inside the anchor band: a realistic DAC countries total.
ANCHOR_VALUE: float = 2e11


def _by_check(results: list[CheckResult]) -> dict[str, CheckResult]:
    """Index results by check name."""
    return {r.check: r for r in results}


def _financing_rows(
    years: tuple[int, ...] = (FINANCING_END,),
    donors: tuple[str, ...] = CRITICAL_DONORS,
    types: tuple[str, ...] = TYPES,
) -> list[dict]:
    """One Total ODA row per donor, year and type, plus the DAC countries anchor rows."""
    return [
        {
            "year": year,
            "donor_name": donor,
            "indicator_name": "Total ODA",
            "type": type_,
            "value_usd_current": ANCHOR_VALUE
            if donor == DAC_COUNTRIES_NAME
            else 1_000_000.0,
            "pct_of_gni": 0.005,
        }
        for year in years
        for donor in (*donors, DAC_COUNTRIES_NAME)
        for type_ in types
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
        {"year": 1980, "rows": (len(CRITICAL_DONORS) + 1) * len(TYPES)}
    ]


def _many_rows(make_view: MakeView, n: int) -> LoadedView:
    """A financing view with n rows, enough to sit below the null error fraction."""
    rows = [
        {
            "year": FINANCING_END,
            "donor_name": f"Donor {i}",
            "indicator_name": "Total ODA",
            "type": "Flows",
            "value_usd_current": 1_000_000.0,
        }
        for i in range(n)
    ]
    return make_view("financing_view", rows)


def test_value_nulls_and_magnitude(make_view: MakeView) -> None:
    """Primary nulls are ERROR, a few other nulls a WARNING, huge values ERROR."""
    view = _many_rows(make_view, int(2 / VALUE_NULL_ERROR_FRACTION))
    data = view.data
    data.loc[0, ["value_usd_current", "value_usd_constant"]] = np.nan
    data.loc[1, ["value_eur_constant", "value_eur_current"]] = np.nan
    data.loc[2, "value_gbp_current"] = MAX_SANE_VALUE * 10
    data.loc[3, "value_cad_current"] = np.inf
    results = _by_check(check_values(view))

    primary = results["contracts.primary_value_populated"]
    assert not primary.passed and primary.severity is Severity.ERROR

    others = results["contracts.values_populated"]
    assert not others.passed
    assert others.severity is Severity.WARNING and not others.blocking
    assert "value_eur_constant: 1" in others.message
    assert len(others.details) == 2  # usd_constant and eur rows

    assert results["contracts.value_null_pairs"].passed

    magnitude = results["contracts.value_magnitude"]
    assert not magnitude.passed and magnitude.message.startswith("2 values")


def test_value_nulls_above_the_fraction_block(financing: LoadedView) -> None:
    """A value column nulled on most rows is an ERROR."""
    financing.data["value_eur_constant"] = np.nan
    results = _by_check(check_values(financing))
    nulls = results["contracts.values_populated"]
    assert not nulls.passed and nulls.severity is Severity.ERROR and nulls.blocking


def test_value_null_pairs(financing: LoadedView) -> None:
    """A constant value null where its current one is set fails, and the reverse."""
    financing.data.loc[0, "value_gbp_constant"] = np.nan
    financing.data.loc[1, "value_cad_current"] = np.nan
    [pairs] = [r for r in check_values(financing) if r.check.endswith("null_pairs")]
    assert not pairs.passed and pairs.severity is Severity.ERROR
    assert len(pairs.details) == 2


def test_missing_critical_donor(make_view: MakeView) -> None:
    """A critical donor without rows fails, once per type."""
    view = make_view("financing_view", _financing_rows(donors=CRITICAL_DONORS[1:]))
    [result] = check_critical_donors(view)
    assert not result.passed
    assert result.details["donor_name"].tolist() == [CRITICAL_DONORS[0]] * len(TYPES)


def test_critical_donor_must_have_the_end_year(make_view: MakeView) -> None:
    """A critical donor with history but no end-year rows fails."""
    history = _financing_rows(years=(FINANCING_END - 1,))
    latest = _financing_rows(donors=CRITICAL_DONORS[1:])
    [result] = check_critical_donors(make_view("financing_view", history + latest))
    assert not result.passed
    assert set(result.details["donor_name"]) == {CRITICAL_DONORS[0]}


def test_critical_donor_checked_per_type(make_view: MakeView) -> None:
    """Financing: a critical donor missing from one type in the end year fails."""
    rows = [
        r
        for r in _financing_rows()
        if not (r["donor_name"] == CRITICAL_DONORS[0] and r["type"] == TYPES[1])
    ]
    [result] = check_critical_donors(make_view("financing_view", rows))
    assert result.details.to_dict("records") == [
        {"series": TYPES[1], "donor_name": CRITICAL_DONORS[0]}
    ]


def test_critical_donors_without_type(make_view: MakeView) -> None:
    """Views without a type column check the end year as one series."""
    rows = [
        {
            "year": get_spec("gender_view").time["end"],
            "donor_name": donor,
            "recipient_name": ODA_ELIGIBLE,
            "indicator_name": "Main target",
            "value_usd_current": 1.0,
        }
        for donor in CRITICAL_DONORS[1:]
    ]
    [result] = check_critical_donors(make_view("gender_view", rows))
    assert result.details.to_dict("records") == [
        {"series": "all", "donor_name": CRITICAL_DONORS[0]}
    ]


@pytest.mark.parametrize(
    ("scale", "passes"),
    [(1.0, True), (1e-6, False), (1e3, False), (ANCHOR_MIN_UNITS / ANCHOR_VALUE, True)],
)
def test_anchor_band(financing: LoadedView, scale: float, passes: bool) -> None:
    """Values scaled out of the anchor band block; the band's edge passes."""
    financing.data["value_usd_current"] *= scale
    [result] = check_anchor(financing)
    assert result.passed is passes
    assert result.severity is Severity.ERROR


def test_anchor_missing_rows_fail(financing: LoadedView) -> None:
    """No DAC countries Total ODA in the end year is a failure, not a pass."""
    financing.data = financing.data[financing.data["donor_name"] != DAC_COUNTRIES_NAME]
    [result] = check_anchor(financing)
    assert not result.passed and "No rows" in result.message


def test_anchor_sums_recipient_views(make_view: MakeView) -> None:
    """Recipient views sum DAC countries to ODA eligible countries over indicators."""
    end = get_spec("recipients_view").time["end"]
    rows = [
        {
            "year": end,
            "donor_name": DAC_COUNTRIES_NAME,
            "recipient_name": ODA_ELIGIBLE,
            "indicator_name": indicator,
            "value_usd_current": ANCHOR_MAX_UNITS * 0.6,
        }
        for indicator in ("Bilateral", "Imputed multilateral")
    ]
    [result] = check_anchor(make_view("recipients_view", rows))
    assert not result.passed  # 1.2 x the ceiling once summed


@pytest.mark.parametrize(
    ("scale", "passes"),
    [
        (0.9, True),
        (CURRENCY_PER_USD_MIN, True),
        (CURRENCY_PER_USD_MAX, True),
        (1e-6, False),
        (1e3, False),
    ],
)
def test_anchor_currencies(financing: LoadedView, scale: float, passes: bool) -> None:
    """EUR on the anchor rows scaled out of the per-USD band blocks; the edges pass."""
    eur = [c for c in financing.data.columns if c.startswith("value_eur")]
    financing.data[eur] *= scale
    [result] = check_anchor_currencies(financing)
    assert result.passed is passes
    assert result.severity is Severity.ERROR
    if not passes:
        assert (result.details["value_eur_current"] == scale).all()


def test_anchor_currencies_recipient_view_and_missing_rows(make_view: MakeView) -> None:
    """Recipient views are checked once; missing anchor rows fail."""
    end = get_spec("recipients_view").time["end"]
    row = {
        "year": end,
        "donor_name": DAC_COUNTRIES_NAME,
        "recipient_name": ODA_ELIGIBLE,
        "indicator_name": "Bilateral",
        "value_usd_current": ANCHOR_VALUE,
        "value_gbp_current": ANCHOR_VALUE * 1e-3,
    }
    [result] = check_anchor_currencies(make_view("recipients_view", [row]))
    assert not result.passed
    assert result.details["value_gbp_current"].tolist() == [1e-3]
    assert result.details["value_eur_current"].tolist() == [1.0]

    other = {**row, "donor_name": "France"}
    [result] = check_anchor_currencies(make_view("recipients_view", [other]))
    assert not result.passed and "No anchor rows" in result.message


def test_gni_share_range_and_population(financing: LoadedView) -> None:
    """pct_of_gni beyond the limit fails; a critical donor's null end-year share fails."""
    assert all(r.passed for r in check_gni_share(financing))
    financing.data["pct_of_gni"] *= 100
    results = _by_check(check_gni_share(financing))
    assert not results["contracts.gni_share_range"].passed
    assert results["contracts.gni_share_populated"].passed

    financing.data["pct_of_gni"] = np.float32(PCT_OF_GNI_LIMIT / 2)
    critical = financing.data["donor_name"] == CRITICAL_DONORS[0]
    financing.data.loc[critical, "pct_of_gni"] = np.nan
    results = _by_check(check_gni_share(financing))
    assert results["contracts.gni_share_range"].passed
    populated = results["contracts.gni_share_populated"]
    assert not populated.passed and populated.blocking
    assert len(populated.details) == len(TYPES)


def test_gni_share_only_in_financing(make_view: MakeView, sector_rows: list) -> None:
    """Views without pct_of_gni get no GNI results."""
    assert check_gni_share(make_view("sectors_view", sector_rows)) == []


def test_types_must_be_exactly_the_financing_types(financing: LoadedView) -> None:
    """An unknown type label and an absent one both fail."""
    assert check_types(financing)[0].passed
    financing.data["type"] = financing.data["type"].replace({"Flows": "flows"})
    [result] = check_types(financing)
    assert not result.passed
    assert set(result.details.itertuples(index=False, name=None)) == {
        ("flows", "unknown"),
        ("Flows", "absent"),
    }


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
